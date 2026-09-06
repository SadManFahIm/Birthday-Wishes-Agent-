Write-Host "Starting folder restructure..." -ForegroundColor Cyan

# Step 1: Create folders
New-Item -ItemType Directory -Path src,src\core,src\ml,src\privacy,src\ops,src\integrations,src\infra,tests,docs -Force | Out-Null

# Step 2: Create __init__.py files
foreach ($f in @("src","src\core","src\ml","src\privacy","src\ops","src\integrations","src\infra","tests")) {
    $p = Join-Path $f "__init__.py"
    if (!(Test-Path $p)) { New-Item -ItemType File -Path $p -Force | Out-Null; git add $p 2>$null }
}

# Step 3: Move Python files with git mv
Write-Host "`nMoving core files..." -ForegroundColor Yellow
if (Test-Path "agent.py") { git mv agent.py src/core/agent.py 2>$null; Write-Host "  agent.py -> src/core/" }
if (Test-Path "contact_loader.py") { git mv contact_loader.py src/core/contact_loader.py 2>$null; Write-Host "  contact_loader.py -> src/core/" }
if (Test-Path "wish_templates.py") { git mv wish_templates.py src/core/wish_templates.py 2>$null; Write-Host "  wish_templates.py -> src/core/" }
if (Test-Path "task_runners.py") { git mv task_runners.py src/core/task_runners.py 2>$null; Write-Host "  task_runners.py -> src/core/" }
if (Test-Path "scheduler.py") { git mv scheduler.py src/core/scheduler.py 2>$null; Write-Host "  scheduler.py -> src/core/" }
if (Test-Path "autonomous_agent.py") { git mv autonomous_agent.py src/core/autonomous_agent.py 2>$null; Write-Host "  autonomous_agent.py -> src/core/" }
if (Test-Path "langgraph_workflow.py") { git mv langgraph_workflow.py src/core/langgraph_workflow.py 2>$null; Write-Host "  langgraph_workflow.py -> src/core/" }
if (Test-Path "mcp_server.py") { git mv mcp_server.py src/core/mcp_server.py 2>$null; Write-Host "  mcp_server.py -> src/core/" }
if (Test-Path "model_config.py") { git mv model_config.py src/core/model_config.py 2>$null; Write-Host "  model_config.py -> src/core/" }

Write-Host "`nMoving ML files..." -ForegroundColor Yellow
if (Test-Path "churn_predictor.py") { git mv churn_predictor.py src/ml/churn_predictor.py 2>$null; Write-Host "  churn_predictor.py -> src/ml/" }
if (Test-Path "roi_forecasting.py") { git mv roi_forecasting.py src/ml/roi_forecasting.py 2>$null; Write-Host "  roi_forecasting.py -> src/ml/" }
if (Test-Path "wish_performance_predictor.py") { git mv wish_performance_predictor.py src/ml/wish_performance_predictor.py 2>$null; Write-Host "  wish_performance_predictor.py -> src/ml/" }
if (Test-Path "interest_graph.py") { git mv interest_graph.py src/ml/interest_graph.py 2>$null; Write-Host "  interest_graph.py -> src/ml/" }
if (Test-Path "vector_memory.py") { git mv vector_memory.py src/ml/vector_memory.py 2>$null; Write-Host "  vector_memory.py -> src/ml/" }
if (Test-Path "conversation_summary.py") { git mv conversation_summary.py src/ml/conversation_summary.py 2>$null; Write-Host "  conversation_summary.py -> src/ml/" }

Write-Host "`nMoving privacy files..." -ForegroundColor Yellow
if (Test-Path "gdpr_compliance.py") { git mv gdpr_compliance.py src/privacy/gdpr_compliance.py 2>$null; Write-Host "  gdpr_compliance.py -> src/privacy/" }
if (Test-Path "audit_log.py") { git mv audit_log.py src/privacy/audit_log.py 2>$null; Write-Host "  audit_log.py -> src/privacy/" }
if (Test-Path "jwt_auth.py") { git mv jwt_auth.py src/privacy/jwt_auth.py 2>$null; Write-Host "  jwt_auth.py -> src/privacy/" }

Write-Host "`nMoving ops files..." -ForegroundColor Yellow
if (Test-Path "push_notifications.py") { git mv push_notifications.py src/ops/push_notifications.py 2>$null; Write-Host "  push_notifications.py -> src/ops/" }
if (Test-Path "rate_limit_dashboard.py") { git mv rate_limit_dashboard.py src/ops/rate_limit_dashboard.py 2>$null; Write-Host "  rate_limit_dashboard.py -> src/ops/" }
if (Test-Path "morning_briefing.py") { git mv morning_briefing.py src/ops/morning_briefing.py 2>$null; Write-Host "  morning_briefing.py -> src/ops/" }
if (Test-Path "engagement_calendar.py") { git mv engagement_calendar.py src/ops/engagement_calendar.py 2>$null; Write-Host "  engagement_calendar.py -> src/ops/" }
if (Test-Path "email_outreach.py") { git mv email_outreach.py src/ops/email_outreach.py 2>$null; Write-Host "  email_outreach.py -> src/ops/" }
if (Test-Path "error_budget.py") { git mv error_budget.py src/ops/error_budget.py 2>$null; Write-Host "  error_budget.py -> src/ops/" }
if (Test-Path "config_validator.py") { git mv config_validator.py src/ops/config_validator.py 2>$null; Write-Host "  config_validator.py -> src/ops/" }
if (Test-Path "structured_logger.py") { git mv structured_logger.py src/ops/structured_logger.py 2>$null; Write-Host "  structured_logger.py -> src/ops/" }
if (Test-Path "db_migrations.py") { git mv db_migrations.py src/ops/db_migrations.py 2>$null; Write-Host "  db_migrations.py -> src/ops/" }

Write-Host "`nMoving integration files..." -ForegroundColor Yellow
if (Test-Path "crm_sync.py") { git mv crm_sync.py src/integrations/crm_sync.py 2>$null; Write-Host "  crm_sync.py -> src/integrations/" }
if (Test-Path "google_calendar_sync.py") { git mv google_calendar_sync.py src/integrations/google_calendar_sync.py 2>$null; Write-Host "  google_calendar_sync.py -> src/integrations/" }
if (Test-Path "notion_sync.py") { git mv notion_sync.py src/integrations/notion_sync.py 2>$null; Write-Host "  notion_sync.py -> src/integrations/" }

Write-Host "`nMoving infra files..." -ForegroundColor Yellow
if (Test-Path "fastapi_backend.py") { git mv fastapi_backend.py src/infra/fastapi_backend.py 2>$null; Write-Host "  fastapi_backend.py -> src/infra/" }
if (Test-Path "postgres_migration.py") { git mv postgres_migration.py src/infra/postgres_migration.py 2>$null; Write-Host "  postgres_migration.py -> src/infra/" }
if (Test-Path "redis_cache.py") { git mv redis_cache.py src/infra/redis_cache.py 2>$null; Write-Host "  redis_cache.py -> src/infra/" }
if (Test-Path "seed_data.py") { git mv seed_data.py src/infra/seed_data.py 2>$null; Write-Host "  seed_data.py -> src/infra/" }

Write-Host "`nMoving test files..." -ForegroundColor Yellow
if (Test-Path "integration_tests.py") { git mv integration_tests.py tests/integration_tests.py 2>$null; Write-Host "  integration_tests.py -> tests/" }
if (Test-Path "api_tests.py") { git mv api_tests.py tests/api_tests.py 2>$null; Write-Host "  api_tests.py -> tests/" }

Write-Host "`nMoving doc files..." -ForegroundColor Yellow
if (Test-Path "PROJECT_STRUCTURE.md") { git mv PROJECT_STRUCTURE.md docs/PROJECT_STRUCTURE.md 2>$null; Write-Host "  PROJECT_STRUCTURE.md -> docs/" }
if (Test-Path "PROJECT_TREE.md") { git mv PROJECT_TREE.md docs/PROJECT_TREE.md 2>$null; Write-Host "  PROJECT_TREE.md -> docs/" }

# Step 4: Move existing subfolders into src/
Write-Host "`nMoving existing folders into src/..." -ForegroundColor Yellow
if (Test-Path "Platforms") { git mv Platforms src/platforms 2>$null; Write-Host "  Platforms/ -> src/platforms/" }
if (Test-Path "ai") { git mv ai src/ai 2>$null; Write-Host "  ai/ -> src/ai/" }
if (Test-Path "automation") { git mv automation src/automation 2>$null; Write-Host "  automation/ -> src/automation/" }
if (Test-Path "contacts") { git mv contacts src/contacts 2>$null; Write-Host "  contacts/ -> src/contacts/" }
if ((Test-Path "security") -and !(Test-Path "src\security")) { git mv security src/security 2>$null; Write-Host "  security/ -> src/security/" }
if (Test-Path "notifications") { git mv notifications src/notifications 2>$null; Write-Host "  notifications/ -> src/notifications/" }
if (Test-Path "detection") { git mv detection src/detection 2>$null; Write-Host "  detection/ -> src/detection/" }
if (Test-Path "multi_account") { git mv multi_account src/multi_account 2>$null; Write-Host "  multi_account/ -> src/multi_account/" }
if (Test-Path "dashboards") { git mv dashboards src/dashboards 2>$null; Write-Host "  dashboards/ -> src/dashboards/" }
if ((Test-Path "config") -and !(Test-Path "src\config")) { git mv config src/config 2>$null; Write-Host "  config/ -> src/config/" }

# Step 5: Cleanup
Write-Host "`nCleaning up..." -ForegroundColor Yellow
git rm -r --cached __pycache__ 2>$null
git rm --cached restructure.ps1 2>$null
git rm --cached cspell.json 2>$null

Write-Host "`nDone! Now run:" -ForegroundColor Cyan
Write-Host "  git status"
Write-Host "  git add -A"
Write-Host "  git commit -m 'refactor: restructure project into src/ layout'"
Write-Host "  git push origin refactor/folder-restructure"
