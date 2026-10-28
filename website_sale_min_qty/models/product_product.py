# -*- coding: utf-8 -*-
from odoo import fields, models

from .min_qty import snap_for, uom_rounding, web_values


class ProductProduct(models.Model):
    _inherit = "product.product"

    # The two columns are declared again on the variant on purpose. They are
    # delegated to the template by ``_inherits`` until a variant declares its
    # own field of that name -- the same way ``lst_price`` lives on both --
    # and that is what lets one variant deviate from its siblings. A value of
    # 0 means "use the template's resolved value", so an untouched variant
    # follows its product and its category without a copy of either number.
    min_order_qty = fields.Float(
        "Minimum Order Quantity", default=0.0, digits="Product Unit",
        help="Overrides the product's minimum for this variant only. 0 uses "
             "the product's value, which itself falls back to the category.",
    )
    qty_step = fields.Float(
        "Quantity Step", default=0.0, digits="Product Unit",
        help="Overrides the product's quantity step for this variant only. "
             "0 uses the product's value, which itself falls back to the "
             "category.",
    )

    def _min_qty_rules(self):
        """``(minimum, step)`` for this variant, overrides applied.

        Read through the template record, not through ``self``: on a variant
        the two columns above hold the *override*, and asking the template's
        resolution with a variant record would answer with the override
        instead of the inherited value.
        """
        self.ensure_one()
        template_minimum, template_step = self.product_tmpl_id._min_qty_rules()
        minimum = self.min_order_qty if self.min_order_qty > 0 else template_minimum
        step = self.qty_step if self.qty_step > 0 else template_step
        return minimum, step

    def _min_qty_has_rules(self):
        minimum, step = self._min_qty_rules()
        return bool(minimum > 0 or step > 0)

    # The helpers below are declared on both models on purpose: ``_inherits``
    # delegates fields, not methods, so a variant has no access to the
    # template's methods at all (which is why core calls
    # ``product.product_tmpl_id._get_combination_info`` rather than the
    # variant). Each one is a two-line bridge to the shared function.
    def _min_qty_rounding(self):
        return uom_rounding(self)

    def _min_qty_snap(self, quantity):
        return snap_for(self, quantity)

    def _min_qty_web_values(self):
        return web_values(self)
