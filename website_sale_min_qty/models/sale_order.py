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
        cart) so the customer reads the reason that is actually theirs.
        """
        violated = self._min_qty_violated_lines()
        if violated:
            raise ValidationError(self._min_qty_checkout_message(violated))
        return super()._check_cart_is_ready_to_be_paid()

    # ------------------------------------------------------------------
    # Cart mutation
    # ------------------------------------------------------------------
    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        """Apply the product's rule to the *new total* of a line.

        This is the method both the cart page and ``_cart_add`` go through
        once the line exists, so it is where a typed quantity becomes an
        allowed one. The warning is attached to the returned values, which is
        what the shop front-end shows as a toast.
        """
        line = self.order_line.filtered(lambda sol: sol.id == line_id)[:1]
        product = line.product_id
        if not product or quantity <= 0 or not product._min_qty_has_rules():
            # A removal (or a line this module cannot place) is handed over
            # untouched: the minimum applies to what is bought, not to what
            # is deleted.
            return super()._cart_update_line_quantity(line_id, quantity, **kwargs)
        target, changed = product._min_qty_snap(quantity)
        values = super()._cart_update_line_quantity(line_id, target, **kwargs)
        if changed:
            values["warning"] = self._min_qty_warning(product, quantity, target)
        return values

    def _cart_add(self, product_id, quantity=1.0, **kwargs):
        """Make the quantity being added an allowed one before the core sees it.

        The core's own add path creates the line without passing through
        ``_cart_update_line_quantity``, so the request has to be snapped here
        too; the total is snapped again once the line exists, which is
        harmless because a sum of grid multiples is itself a multiple.
        """
        product = self.env["product.product"].browse(int(product_id or 0)).exists()
        if not product or quantity <= 0 or not product._min_qty_has_rules():
            return super()._cart_add(product_id, quantity, **kwargs)
        target, changed = product._min_qty_snap(quantity)
        values = super()._cart_add(product_id, target, **kwargs)
        if changed:
            values["warning"] = self._min_qty_warning(product, quantity, target)
        return values
