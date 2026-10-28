# -*- coding: utf-8 -*-
from odoo import fields, models

from .min_qty import snap_for, uom_rounding, web_values


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    min_order_qty = fields.Float(
        "Minimum Order Quantity", default=0.0, digits="Product Unit",
        help="Smallest quantity a customer may order from a product in this "
             "category. 0 lets the parent category decide; a product with its "
             "own minimum always wins over the category.",
    )
    qty_step = fields.Float(
        "Quantity Step", default=0.0, digits="Product Unit",
        help="Quantities are sold in multiples of this number. 0 lets the "
             "parent category decide and, if no category sets one, means the "
             "quantity is free.",
    )

    def _min_qty_resolved(self, field_name):
        """This category's value for *field_name*, or the nearest ancestor's.

        The walk stops at the first non-zero value, nearest category first, so
        a sub-category can tighten its parent without repeating the other
        column. A visited set keeps a corrupted parent loop from hanging the
        shop.
        """
        self.ensure_one()
        seen = self.browse()
        category = self
        while category:
            value = category[field_name]
            if value > 0:
                return value
            seen |= category
            category = category.parent_id - seen
        return 0.0


class ProductTemplate(models.Model):
    _inherit = "product.template"

    min_order_qty = fields.Float(
        "Minimum Order Quantity", default=0.0, digits="Product Unit",
        help="Smallest quantity a customer may order on the website. 0 "
             "inherits the value of the product's public category (and of its "
             "parents); 0 everywhere means no minimum.",
    )
    qty_step = fields.Float(
        "Quantity Step", default=0.0, digits="Product Unit",
        help="Website quantities are sold in multiples of this number, and "
             "anything in between is rounded up to the next multiple. 0 "
             "inherits the category and, failing that, leaves the quantity "
             "free.",
    )

    # ------------------------------------------------------------------
    # Resolving the rules
    # ------------------------------------------------------------------
    def _min_qty_category_value(self, field_name):
        """The first value found on the product's public categories.

        A product can sit in several categories. The lowest id wins, then that
        category's own parents -- stated here because "inherited from the
        category" has to mean one thing when two categories disagree, and a
        merchant reordering categories should not silently change it.
        """
        self.ensure_one()
        for category in self.public_categ_ids.sorted("id"):
            value = category._min_qty_resolved(field_name)
            if value > 0:
                return value
        return 0.0

    def _min_qty_rules(self):
        """``(minimum, step)`` for this template, category inheritance applied.

        The two columns resolve independently: a product may take its minimum
        from its category and its step from its own form, which is the useful
        combination for "at least one box, in halves".
        """
        self.ensure_one()
        minimum = self.min_order_qty
        if minimum <= 0:
            minimum = self._min_qty_category_value("min_order_qty")
        step = self.qty_step
        if step <= 0:
            step = self._min_qty_category_value("qty_step")
        return minimum, step

    def _min_qty_has_rules(self):
        minimum, step = self._min_qty_rules()
        return bool(minimum > 0 or step > 0)

    def _min_qty_rounding(self):
        return uom_rounding(self)

    def _min_qty_snap(self, quantity):
        return snap_for(self, quantity)

    def _min_qty_web_values(self):
        return web_values(self)

    def _get_combination_info(self, *args, **kwargs):
        """Add the rule values to the dict the product page already renders.

        ``combination_info`` is the one place the product page and its variant
        selector agree on what is being displayed, so the values ride along
        instead of being looked up a second time in the template -- a second
        lookup is where a template starts showing the template's rules while
        the server enforces the variant's.
        """
        info = super()._get_combination_info(*args, **kwargs)
        variant = self.env["product.product"].browse(info.get("product_id") or 0).exists()
        if not variant:
            variant = self.product_variant_id
        info.update(variant._min_qty_web_values())
        return info
