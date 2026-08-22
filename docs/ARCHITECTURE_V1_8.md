# V1.8 Architecture — Model Evaluation & Production Monitoring

V1.8 adds the governance loop around V1.7 predictive models:

`Dataset Registry -> Offline Evaluation -> Champion/Challenger -> Production Monitoring -> Drift -> Promotion/Rollback`

## Components
- `ModelDatasetRegistry`: versioned evaluation datasets.
- `ModelEvaluationService`: MAE/RMSE for regression/RUL and precision/recall/F1/false-alarm/miss-rate for binary tasks.
- `ModelDeploymentManager`: governed champion/challenger slots with promotion and rollback history.
- `ModelMonitoringService`: feature baseline and mean-shift drift monitoring.
- UI version: sourced dynamically from `/health`; sidebar, top bar, admin and graph editor remain consistent with backend version.

The current drift score is an interpretable engineering indicator based on standardized mean shift. It is not a replacement for production PSI/KS/Wasserstein monitoring; enterprise adapters can extend the service later.
