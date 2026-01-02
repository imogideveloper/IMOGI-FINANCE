import datetime
import sys
import types


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))

if not hasattr(frappe, "_"):
    frappe._ = lambda msg: msg
if not hasattr(frappe, "_dict"):
    def _make_dict(*args, **kwargs):
        if args and isinstance(args[0], dict):
            data = args[0].copy()
            data.update(kwargs)
            return types.SimpleNamespace(**data)
        return types.SimpleNamespace(**kwargs)

    frappe._dict = _make_dict
if not hasattr(frappe, "msgprint"):
    frappe.msgprint = lambda *args, **kwargs: None
if not hasattr(frappe, "bold"):
    frappe.bold = lambda msg: msg
if not hasattr(frappe, "whitelist"):
    frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
if not hasattr(frappe, "throw"):
    class ThrowMarker(Exception):
        pass

    def _throw(msg=None, title=None):
        raise ThrowMarker(msg or title)

    frappe.ThrowMarker = ThrowMarker
    frappe.throw = _throw
if not hasattr(frappe, "get_roles"):
    frappe.get_roles = lambda *args, **kwargs: []
frappe.get_doc = getattr(frappe, "get_doc", lambda *args, **kwargs: None)
frappe.get_all = getattr(frappe, "get_all", lambda *args, **kwargs: [])
frappe.get_cached_doc = getattr(frappe, "get_cached_doc", lambda *args, **kwargs: None)
frappe.new_doc = getattr(frappe, "new_doc", lambda *args, **kwargs: types.SimpleNamespace())
frappe.get_list = getattr(frappe, "get_list", lambda *args, **kwargs: [])
frappe.session = getattr(frappe, "session", frappe._dict(user="Administrator"))

db = getattr(frappe, "db", types.SimpleNamespace())
db.has_column = getattr(db, "has_column", lambda *args, **kwargs: False)
db.get_value = getattr(db, "get_value", lambda *args, **kwargs: None)
db.exists = getattr(db, "exists", lambda *args, **kwargs: False)
db.sql = getattr(db, "sql", lambda *args, **kwargs: None)
frappe.db = db

frappe.model = getattr(frappe, "model", types.SimpleNamespace())
frappe.model.document = getattr(
    frappe.model, "document", types.SimpleNamespace(Document=type("Document", (), {}))
)
sys.modules.setdefault("frappe.model", frappe.model)
sys.modules.setdefault("frappe.model.document", frappe.model.document)

utils = sys.modules.setdefault("frappe.utils", types.ModuleType("frappe.utils"))
utils.now_datetime = getattr(utils, "now_datetime", lambda: datetime.datetime.now())
utils.flt = getattr(utils, "flt", lambda value, *args, **kwargs: float(value or 0))
utils.get_first_day = getattr(utils, "get_first_day", lambda date_str=None: None)
utils.get_last_day = getattr(utils, "get_last_day", lambda date_obj=None: None)
utils.nowdate = getattr(utils, "nowdate", lambda: "")
utils.cint = getattr(utils, "cint", lambda value, *args, **kwargs: int(value or 0))
utils.getdate = getattr(utils, "getdate", lambda value=None: value)
sys.modules["frappe.utils"] = utils

xlsxutils = sys.modules.setdefault("frappe.utils.xlsxutils", types.ModuleType("frappe.utils.xlsxutils"))
xlsxutils.make_xlsx = getattr(
    xlsxutils, "make_xlsx", lambda data, *_args, **_kwargs: types.SimpleNamespace(getvalue=lambda: b"")
)
