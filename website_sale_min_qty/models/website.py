# -*- coding: utf-8 -*-
from odoo import fields, models

from .min_qty import format_quantity, translate


class Website(models.Model):
    _inherit = "website"

    min_qty_message = fields.Char(
        "Minimum Quantity Message", translate=True,
        help="Sentence shown under the quantity input when a product has a "
             "minimum or a step. Leave empty for the default wording. "
             "{min} and {step} are replaced with the product's numbers.",
    )

    def _min_qty_note(self, minimum, step):
        """The sentence printed next to the quantity input.

        A merchant sentence wins, because the useful note is often not about
        the numbers at all ("sold in full boxes, we ship on Mondays"). The
        placeholders are filled only when they are there, and a stray brace in
        a hand-typed sentence falls back to the sentence as written instead of
        rising through the page render.
        """
        self.ensure_one()
        if not minimum and not step:
            return ""
        if self.min_qty_message:
            try:
                return self.min_qty_message.format(
                    min=format_quantity(minimum), step=format_quantity(step))
            except (KeyError, IndexError, ValueError):
                return self.min_qty_message
        if minimum and step:
            return translate(
                self.env,
                "Minimum order: %(min)s, sold in multiples of %(step)s.") % {
                    "min": format_quantity(minimum), "step": format_quantity(step)}
        if minimum:
            return translate(self.env, "Minimum order: %(min)s.") % {
                "min": format_quantity(minimum)}
        return translate(self.env, "Sold in multiples of %(step)s.") % {
            "step": format_quantity(step)}
