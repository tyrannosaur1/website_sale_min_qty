# -*- coding: utf-8 -*-
"""Tell the model which quantity the customer typed; enforce nothing here.

Both cart routes cast the quantity to ``int`` before doing anything with it
("Do not allow float values in ecommerce by default"), which is a reasonable
default and exactly what a 0.25 kg step is not. Rewriting either route to keep
the float would mean copying the combo, optional-product and custom-attribute
plumbing the core does *after* that cast, and each route would need its own
copy -- the copy is also what silently skipped those products before.

So the routes rewrite nothing: they only report the typed quantity, and
``sale.order`` applies the rule once, where every entry point necessarily
arrives (product page, quick add, combo item, optional product, cart edit).
"""
from odoo.http import request, route

from odoo.addons.website_sale.controllers.cart import Cart


class CartMinQty(Cart):

    def _min_qty_typed(self, product, quantity):
        """The typed quantity, when the core cast would actually lose something."""
        if not product or not product._min_qty_has_rules():
            return None
        try:
            typed = float(quantity)
        except (TypeError, ValueError):
            return None
        if typed == int(typed):
            # A whole number survives ``int()`` untouched: let the core work.
            return None
        return typed

    @route(route="/shop/cart/update", type="jsonrpc", auth="public",
           methods=["POST"], website=True, sitemap=False)
    def update_cart(self, line_id, quantity, product_id=None, **kwargs):
        line = request.env["sale.order.line"].sudo().browse(int(line_id or 0)).exists()
        product = line.product_id or request.env["product.product"].browse(
            int(product_id or 0)).exists()
        typed = self._min_qty_typed(product, quantity)
        if typed is not None:
            kwargs["_min_qty_requested"] = {product.id: typed}
        return super().update_cart(line_id, quantity, product_id=product_id, **kwargs)

    @route(route="/shop/cart/add", type="jsonrpc", auth="public",
           methods=["POST"], website=True, sitemap=False)
    def add_to_cart(self, product_template_id, product_id, quantity, uom_id=None,
                    product_custom_attribute_values=None,
                    no_variant_attribute_value_ids=None, linked_products=None, **kwargs):
        product = self.env["product.product"].browse(int(product_id or 0)).exists()
        typed = self._min_qty_typed(product, quantity)
        if typed is not None:
            # Combos, optional products and custom attributes all leave this
            # route through the same model method; the typed quantity rides
            # along keyed by product, so the combo items keep their own.
            kwargs["_min_qty_requested"] = {product.id: typed}
        return super().add_to_cart(
            product_template_id, product_id, quantity, uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            linked_products=linked_products, **kwargs)
