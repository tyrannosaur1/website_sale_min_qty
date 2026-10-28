# -*- coding: utf-8 -*-
"""The two cart routes, only for the quantities the core cannot take.

19.0 and 20.0 cast the quantity of both cart routes to ``int`` before doing
anything with it ("Do not allow float values in ecommerce by default"), which
is a reasonable default and exactly what a 0.25 kg step is not. A fractional
request is therefore handled here, against the model methods that do accept
floats; every integer request -- and every request for a product without a
rule -- is handed to the core method untouched.
"""
from odoo.http import request, route

from odoo.addons.website_sale.controllers.cart import Cart


class CartMinQty(Cart):

    def _min_qty_fractional(self, product, quantity):
        """The requested quantity when it is fractional *and* the product has a rule."""
        if not product or not product._min_qty_has_rules():
            return None
        try:
            wanted = float(quantity)
        except (TypeError, ValueError):
            return None
        if wanted == int(wanted):
            return None
        return wanted

    @route(route="/shop/cart/update", type="jsonrpc", auth="public",
           methods=["POST"], website=True, sitemap=False)
    def update_cart(self, line_id, quantity, product_id=None, **kwargs):
        line = request.env["sale.order.line"].sudo().browse(int(line_id or 0)).exists()
        wanted = self._min_qty_fractional(line.product_id, quantity)
        if wanted is None:
            return super().update_cart(line_id, quantity, product_id=product_id, **kwargs)

        order_sudo = request.cart
        values = order_sudo._cart_update_line_quantity(line.id, wanted, **kwargs)
        # The cart page redraws itself from these, so a fractional quantity
        # has to bring back the same payload the core route would have sent.
        values.update(self._get_updated_cart_page_values(order_sudo))
        values["website_sale.quick_reorder_history"] = self.env.website._render_template(
            "website_sale.quick_reorder_history",
            {"website_sale_order": order_sudo, **self._prepare_order_history()})
        return values

    @route(route="/shop/cart/add", type="jsonrpc", auth="public",
           methods=["POST"], website=True, sitemap=False)
    def add_to_cart(self, product_template_id, product_id, quantity, uom_id=None,
                    product_custom_attribute_values=None,
                    no_variant_attribute_value_ids=None, linked_products=None, **kwargs):
        product = self.env["product.product"].browse(int(product_id or 0)).exists()
        wanted = self._min_qty_fractional(product, quantity)
        if wanted is None or linked_products or product_custom_attribute_values \
                or no_variant_attribute_value_ids:
            # Combos, optional products and custom attributes keep the core
            # path: their quantities are integers by construction, and
            # re-implementing that plumbing here would be a copy to maintain.
            return super().add_to_cart(
                product_template_id, product_id, quantity, uom_id=uom_id,
                product_custom_attribute_values=product_custom_attribute_values,
                no_variant_attribute_value_ids=no_variant_attribute_value_ids,
                linked_products=linked_products, **kwargs)

        order_sudo = request.cart or self.env.website._create_cart()
        values = order_sudo.with_context(skip_cart_verification=True)._cart_add(
            product_id=product.id, quantity=wanted, uom_id=uom_id, **kwargs)
        order_sudo._verify_cart_after_update()

        notifications = []
        info = self._get_cart_notification_information(
            order_sudo, {values["line_id"]: values["added_qty"]})
        if info:
            notifications.append({"type": "item_added", "data": info})
        warning = values.get("warning", "")
        if warning:
            (order_sudo.order_line.filtered(
                lambda line: line.id == values["line_id"]) or order_sudo
             )._add_warning_alert(warning)
            notifications.append({"type": "warning",
                                  "data": {"warning_message": warning}})
        return {
            "cart_quantity": order_sudo.cart_quantity,
            "notifications": notifications,
            "quantity": values.get("quantity", 0),
            "tracking_info": values.get("tracking_info", []),
            "currency": order_sudo.currency_id.name,
        }
