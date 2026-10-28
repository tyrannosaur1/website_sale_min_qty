# -*- coding: utf-8 -*-
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleMinQty(WebsiteSale):

    def checkout_redirection(self, order):
        """Send the customer back to the cart before a checkout they cannot pay.

        16.0 has no model hook for this: ``/shop/checkout`` and ``/shop/payment``
        both ask this method first (empty cart, state, login), so the rule is
        checked in the same place as the ones it belongs with. Later series
        raise from ``sale.order`` instead, where the same check sits before the
        payment page.

        Only a *cart* is refused here. A line that is already below a minimum
        the merchant raised afterwards is left alone on the cart page -- the
        customer is told, and the checkout waits until they adjust it.
        """
        redirection = super().checkout_redirection(order)
        if redirection:
            return redirection
        if order and order._min_qty_violated_lines():
            return request.redirect("/shop/cart?min_qty_blocked=1")
        return None
