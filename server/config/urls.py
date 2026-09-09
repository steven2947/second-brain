"""仅登记已实现的服务路由，不提供模型或登录占位接口。"""

from django.urls import path

from .health import live, ready
from accounts import views as accounts
from knowledge import views as knowledge
from problems import views as problems
from runs import views as runs
from answers import views as answers
from personal import views as personal
from learning import views as learning
from administration import views as administration
from publishing import views as publishing
from adminops import views as adminops
from operations import views as privacy

urlpatterns = [
    path('api/v1/auth/password-reset/request', accounts.reset_request, name='auth-reset-request'),
    path('api/v1/auth/password-reset/confirm', accounts.reset_confirm, name='auth-reset-confirm'),
    path('api/v1/me/exports', privacy.exports, name='privacy-exports'),
    path('api/v1/me/exports/<uuid:export_id>', privacy.export_detail, name='privacy-export'),
    path('api/v1/me/exports/<uuid:export_id>/download', privacy.export_download, name='privacy-download'),
    path('api/v1/me/trash', privacy.trash, name='privacy-trash'),
    path('api/v1/me/deletion', privacy.deletion, name='privacy-deletion'),
    path('api/v1/problems/<uuid:problem_id>/restore', privacy.restore, name='privacy-restore'),
    path('api/v1/admin/users/<uuid:user_id>/status', adminops.status, name='admin-user-status'),
    path('api/v1/admin/users/<uuid:user_id>/quota', adminops.quota, name='admin-user-quota'),
    path('api/v1/admin/invitations', adminops.invitation, name='admin-invitations'),
    path('api/v1/admin/operations', adminops.operations, name='admin-operations'),
    path('api/v1/admin/feedback/summary', adminops.feedback, name='admin-feedback-summary'),
    path('api/v1/admin/sources', publishing.sources, name='admin-sources'),
    path('api/v1/admin/releases/import', publishing.import_release, name='admin-import-release'),
    path('api/v1/admin/imports', publishing.imports, name='admin-imports'),
    path('api/v1/admin/imports/<uuid:job_id>', publishing.import_detail, name='admin-import-detail'),
    path('api/v1/admin/releases', publishing.releases, name='admin-releases'),
    path('api/v1/admin/releases/<uuid:release_id>', publishing.release_detail, name='admin-release-detail'),
    path('api/v1/admin/releases/<uuid:release_id>/rights', publishing.rights, name='admin-rights'),
    path('api/v1/admin/releases/<uuid:release_id>/publish', publishing.publish, name='admin-publish'),
    path('api/v1/admin/releases/<uuid:release_id>/revoke', publishing.revoke, name='admin-revoke'),
    path('api/v1/admin/users', publishing.users, name='admin-users'),
    path('api/v1/admin/users/<uuid:user_id>/grants/<uuid:release_id>', publishing.grant, name='admin-grant'),
    path("api/v1/admin/auth/login", administration.login, name="admin-login"),
    path("api/v1/admin/me", administration.me, name="admin-me"),
    path("api/v1/admin/auth/reauth", administration.reauth, name="admin-reauth"),
    path("api/v1/admin/auth/logout", administration.logout, name="admin-logout"),
    path("api/v1/learning", learning.collection, name="learning-collection"),
    path("api/v1/learning/<uuid:session_id>", learning.detail, name="learning-detail"),
    path("api/v1/learning/<uuid:session_id>/messages", learning.messages, name="learning-messages"),
    path("api/v1/learning/<uuid:session_id>/archive", learning.archive, name="learning-archive"),
    path("api/v1/learning/<uuid:session_id>/jobs/<uuid:job_id>", learning.job_detail, name="learning-job"),
    path("api/v1/learning/<uuid:session_id>/jobs/<uuid:job_id>/cancel", learning.cancel, name="learning-cancel"),
    path("api/v1/bookmarks", personal.bookmarks, name="personal-bookmarks"),
    path("api/v1/bookmarks/<uuid:release_id>/<str:card_id>", personal.bookmark, name="personal-bookmark"),
    path("api/v1/actions", personal.actions, name="personal-actions"),
    path("api/v1/actions/<uuid:action_id>", personal.action, name="personal-action"),
    path("api/v1/feedback", personal.feedback, name="personal-feedback"),
    path("api/v1/answers/<uuid:answer_id>", answers.detail, name="answer-detail"),
    path("api/v1/problems/<uuid:problem_id>/messages", runs.messages, name="problem-messages"),
    path("api/v1/problems/<uuid:problem_id>/analyze", runs.analyze, name="problem-analyze"),
    path("api/v1/runs/<uuid:run_id>", runs.run_detail, name="run-detail"),
    path("api/v1/jobs/<uuid:job_id>", runs.job_detail, name="job-detail"),
    path("api/v1/jobs/<uuid:job_id>/cancel", runs.cancel, name="job-cancel"),
    path("api/v1/problems", problems.collection, name="problem-collection"),
    path("api/v1/problems/<uuid:problem_id>", problems.detail, name="problem-detail"),
    path("api/v1/libraries", knowledge.libraries, name="knowledge-libraries"),
    path("api/v1/libraries/<uuid:release_id>/books", knowledge.books, name="knowledge-books"),
    path("api/v1/libraries/<uuid:release_id>/books/<path:book_id>", knowledge.book, name="knowledge-book"),
    path("api/v1/libraries/<uuid:release_id>/cards", knowledge.cards, name="knowledge-cards"),
    path("api/v1/libraries/<uuid:release_id>/cards/<path:card_id>", knowledge.card, name="knowledge-card"),
    path("api/v1/libraries/<uuid:release_id>/evidence/<path:evidence_id>", knowledge.evidence, name="knowledge-evidence"),
    path("api/v1/auth/options", accounts.options, name="auth-options"),
    path("api/v1/auth/csrf", accounts.csrf, name="auth-csrf"),
    path("api/v1/auth/register", accounts.register, name="auth-register"),
    path("api/v1/auth/login", accounts.login, name="auth-login"),
    path("api/v1/auth/logout", accounts.logout, name="auth-logout"),
    path("api/v1/auth/logout-all", accounts.logout_all, name="auth-logout-all"),
    path("api/v1/me", accounts.me, name="account-me"),
    path("api/v1/me/password", accounts.password, name="account-password"),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
]
