# Copyright (c) 2024, Imogi Finance and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class TransferApplicationItem(Document):
	def validate(self):
		if self.amount and not self.expected_amount:
			self.expected_amount = self.amount
