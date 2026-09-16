"""Explicit domain permissions. Unknown operations and deleted profiles fail closed."""
import json
from fastapi import HTTPException
from .models import AccessProfile, Workspace

PERMISSIONS = {
 'reports.read': 'View source reports and processing progress',
 'reports.import': 'Import PDFs or start permitted scraping',
 'reports.control': 'Retry and cancel processing',
 'reports.delete': 'Delete source reports',
 'reports.export': 'Download original PDFs and export report content',
 'reviews.read': 'View upgrade reviews',
 'reviews.write': 'Create/edit reviews, decisions and checklists',
 'reviews.delete': 'Delete upgrade reviews',
 'reviews.export': 'Export review packages',
 'audit.read': 'Read domain audit history',
}
BUILTINS = {'admin': list(PERMISSIONS), 'reviewer': list(PERMISSIONS),
 'viewer': ['reports.read','reports.export','reviews.read','reviews.export','audit.read']}

def profile_permissions(db, role):
    if role in BUILTINS: return BUILTINS[role]
    profile = db.get(AccessProfile, role) if role else None
    return json.loads(profile.permissions_json) if profile else None


def operation(request):
    p=request.url.path.rstrip('/'); m=request.method
    if p == '/api/auth/audit': return 'audit.read'
    if p == '/api/releases': return 'reports.read'
    if p.startswith('/api/jobs'):
        if '/files/' in p or p.endswith('/export'): return 'reports.export'
        if m in ('GET','HEAD','OPTIONS') or p.endswith('/view'): return 'reports.read'
        if m == 'DELETE': return 'reports.delete'
        if p.endswith(('/cancel','/retry')): return 'reports.control'
        if p.endswith('/title') and m == 'PUT': return 'reports.import'
        if p in ('/api/jobs','/api/jobs/upload'): return 'reports.import'
    if p.startswith('/api/reviews'):
        if p.endswith('/export'): return 'reviews.export'
        if m in ('GET','HEAD','OPTIONS'): return 'reviews.read'
        if m == 'DELETE' and '/jobs/' not in p: return 'reviews.delete'
        return 'reviews.write'
    return None


def require_workspace_permission(request, db, user, workspace_id, role):
    permission=operation(request)
    allowed=profile_permissions(db,role) or []
    if permission is None or permission not in allowed:
        raise HTTPException(403, 'Your domain access profile does not allow this operation.')
    # Export/view are POST but read-only. Domain state protects modifications, including admin writes.
    space=db.get(Workspace,workspace_id)
    if space.state != 'active' and permission in {'reports.import','reports.control','reports.delete','reviews.write','reviews.delete'}:
        raise HTTPException(403, 'This domain is read-only or archived. An administrator must reactivate it first.')
