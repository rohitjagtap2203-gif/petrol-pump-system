# TODO - Petrol Pump Management (Flask + MongoDB)

## 1) Repo analysis
- [x] Checked existing code/routes/templates references
- [x] Identified legacy SQL usage that must be removed

## 2) Backend rewrite (MongoDB-only)
- [ ] Rewrite `app.py` from scratch (Flask routes, session auth, role-based access, MongoDB CRUD/aggregations)
- [ ] Ensure required routes exist with exact paths
- [ ] Implement dashboard analytics using MongoDB aggregate pipelines
- [ ] Implement inventory stock updates and `/api/fuel-status`
- [ ] Implement employee management (stored in `users` collection)
- [ ] Implement customer management (stored in `customers` collection)
- [ ] Implement sales recording (stored in `sales` collection) + stock decrement + bill id generation
- [ ] Implement `/bill/pdf/<bill_id>` using PDF service
- [ ] Implement `/api/dashboard/charts` using aggregate pipelines

## 3) PDF service rewrite
- [ ] Rewrite `services/pdf_service.py` to remove sqlite3 usage
- [ ] Fetch bill from MongoDB `sales` collection
- [ ] Generate PDF via ReportLab

## 4) Configuration & bootstrap
- [ ] Rewrite `config.py` for MongoDB Atlas + Flask sessions
- [ ] Ensure index creation + default admin + default fuel initialization happen at startup
- [ ] Fix/adjust `mongo/db.py` and `mongo/helpers.py` if needed to support above

## 5) Deployment files
- [ ] Rewrite `requirements.txt` (Flask, PyMongo, Flask-WTF, Gunicorn, ReportLab, python-dotenv)
- [ ] Ensure `render.yaml` is Render-compatible with gunicorn `app:app`
- [ ] Ensure `Procfile` is correct
- [ ] Rewrite `.env.example` with required env vars

## 6) Validation
- [ ] `pip install -r requirements.txt`
- [ ] Smoke test routes: /login, /, /sales, /inventory, /employees, /customers, /reports
- [ ] Verify `/api/dashboard/charts` and `/api/fuel-status`
- [ ] Verify PDF download works for existing bills

