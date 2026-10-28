# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

from .min_qty import format_quantity, is_on_grid, translate


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # Reading the rules off a cart
    # ------------------------------------------------------------------
    def _min_qty_violated_lines(self):
        """The lines that are below their minimum or off their step grid.

        Lines are read, never rewritten: a rule changed by the merchant does
        not move quantities that are already in a cart (the customer sees the
        price they saw when they added the product). The same check is used to
        refuse the checkout, so the two can never disagree about which line is
        the problem.
        """
        self.ensure_one()
        violated = self.env["sale.order.line"]
        for line in self.order_line:
            product = line.product_id
            if not product or getattr(line, "is_delivery", False):
                continue
            minimum, step = product._min_qty_rules()
            if minimum <= 0 and step <= 0:
                continue
            rounding = product._min_qty_rounding()
            quantity = line.product_uom_qty
            if minimum > 0 and float_compare(
                    quantity, minimum, precision_rounding=rounding) < 0:
                violated |= line
            elif step > 0 and not is_on_grid(quantity, step, rounding):
                violated |= line
        return violated

    def _min_qty_warning(self, product, requested, target):
        """Tell the customer what was ordered instead of what they typed."""
        minimum, step = product._min_qty_rules()
        numbers = {
            "product": product.display_name,
            "minimum": format_quantity(minimum),
            "step": format_quantity(step),
            "requested": format_quantity(requested),
            "target": format_quantity(target),
        }
        if step > 0:
            return translate(
                self.env,
                "%(product)s is sold in multiples of %(step)s: the quantity "
                "was changed from %(requested)s to %(target)s.") % numbers
        return translate(
            self.env,
            "%(product)s has a minimum order quantity of %(minimum)s: the "
            "quantity was changed from %(requested)s to %(target)s.") % numbers

    def _min_qty_rule_text(self, product):
        """``Product (at least 5, in multiples of 2)`` for the checkout error."""
        minimum, step = product._min_qty_rules()
        numbers = {
            "product": product.display_name,
            "minimum": format_quantity(minimum),
            "step": format_quantity(step),
        }
        if minimum and step:
            return translate(
                self.env, "%(product)s (at least %(minimum)s, in multiples of "
                "%(step)s)") % numbers
        if minimum:
            return translate(self.env, "%(product)s (at least %(minimum)s)") % numbers
        return translate(self.env, "%(product)s (in multiples of %(step)s)") % numbers

    def _min_qty_checkout_message(self, lines):
        return translate(
            self.env,
            "The cart cannot go to the checkout yet: %(lines)s. Please change "
            "the quantities in your cart.") % {
                "lines": ", ".join(self._min_qty_rule_text(line.product_id)
                                   for line in lines)}

    # ------------------------------------------------------------------
    # Hook used by the payment page
    # ------------------------------------------------------------------
    def _check_cart_is_ready_to_be_paid(self):
        """Refuse the checkout while a line is below its rule.

        Checked before the core's own conditions (a delivery method, an empty
        cart) so the customer reads the reason that is actually theirs, and
        because those conditions differ from one series to the next while this
        one does not.
        """
        violated = self._min_qty_violated_lines()
        if violated:
            raise ValidationError(self._min_qty_checkout_message(violated))
        return super()._check_cart_is_ready_to_be_paid()

    # ------------------------------------------------------------------
    # The single choke point every cart mutation goes through
    # ------------------------------------------------------------------
    def _min_qty_option_ids(self, order_line):
        """The option lines of *order_line*, under either of the two names.

        ``option_line_ids`` was renamed ``linked_line_ids`` in 18.0; the field
        is looked up rather than assumed so one release does not have to keep
        a copy of this method.
        """
        for name in ("option_line_ids", "linked_line_ids"):
            if name in order_line._fields:
                return list(set(order_line[name].filtered(
                    lambda line: line.order_id == order_line.order_id).ids))
        return []

    def _cart_update(self, product_id, line_id=None, add_qty=0, set_qty=0, **kwargs):
        """Apply the product's minimum and step before the line is written.

        16.0 to 18.0 cast the requested quantity to ``int`` before computing
        the new line quantity, which is exactly what a 0.25 kg step cannot
        survive. The request is therefore resolved to a quantity here, on the
        float, and integral results are handed back to the core method so its
        stock checks, zero-price guard and delivery recalculation keep running
        unchanged. Only a genuinely fractional result -- the case the core
        cannot represent -- writes the line itself.
        """
        product = self.env["product.product"].browse(int(product_id or 0)).exists()
        if not product:
            return super()._cart_update(product_id, line_id=line_id,
                                        add_qty=add_qty, set_qty=set_qty, **kwargs)
        minimum, step = product._min_qty_rules()
        if minimum <= 0 and step <= 0:
            # Nothing configured: the request is not touched at all, which is
            # the promise this module makes to shops that never use it.
            return super()._cart_update(product_id, line_id=line_id,
                                        add_qty=add_qty, set_qty=set_qty, **kwargs)

        # "Add nothing" is not an order: the core reads it as a removal
        # (``add_qty`` None) or as a no-op (0), and both meanings survive only
        # if the request is handed over exactly as it came in.
        if not set_qty and not add_qty:
            return super()._cart_update(product_id, line_id=line_id,
                                        add_qty=add_qty, set_qty=set_qty, **kwargs)

        if line_id is not False:
            order_line = self._cart_find_product_line(product_id, line_id, **kwargs)[:1]
        else:
            order_line = self.env["sale.order.line"]

        try:
            add_qty = float(add_qty or 0.0)
        except (TypeError, ValueError):
            add_qty = 1.0
        try:
            set_qty = float(set_qty or 0.0)
        except (TypeError, ValueError):
            set_qty = 0.0

        if set_qty:
            requested = set_qty
        elif order_line:
            requested = order_line.product_uom_qty + add_qty
        else:
            requested = add_qty

        if requested <= 0:
            # Removing a line (or a no-op) is never an order: the minimum must
            # not turn "delete this" into "buy five".
            return super()._cart_update(product_id, line_id=line_id,
                                        add_qty=add_qty, set_qty=set_qty, **kwargs)

        target, changed = product._min_qty_snap(requested)
        warning = (self._min_qty_warning(product, requested, target)
                   if changed else "")

        if target == int(target):
            result = super()._cart_update(product_id, line_id=line_id,
                                          add_qty=0, set_qty=int(target), **kwargs)
            if warning:
                result["warning"] = warning
            return result

        quantity, stock_warning = self._verify_updated_quantity(
            order_line, product_id, target, **kwargs)
        order_line = self._cart_update_order_line(product_id, quantity, order_line, **kwargs)
        return {
            "line_id": order_line.id,
            "quantity": quantity,
            "option_ids": self._min_qty_option_ids(order_line),
            "warning": warning or stock_warning,
        }
