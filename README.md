# Student Dropout Risk Prediction

An XGBoost-powered system that predicts student dropout risk with a web-based dashboard featuring three role-based views: **Student**, **Faculty**, and **Admin**.

![Dashboard Preview](frontend/index.html)

## Project Structure

```
student-dropout-prediction/
├── backend/                    # Flask API server
│   ├── __init__.py
│   ├── app.py                  # Main Flask application
│   └── model_service.py        # Model loading & prediction logic
├── frontend/                   # Web dashboard
│   ├── index.html              # Single-page dashboard
│   ├── css/style.css           # Modern responsive styling
│   └── js/app.js               # Frontend JavaScript
├── src/                        # ML pipeline
│   ├── __init__.py
│   ├── data_loader.py          # Data loading & validation
│   ├── preprocess.py           # Config-driven preprocessing pipeline
│   ├── train.py                # Config-driven model training & evaluation
│   ├── pipeline.py             # Main orchestrator
│   ├── preprocessing_pipeline.py # XGBoost preprocessing (engineered features)
│   ├── train_xgboost.py        # Train/tune the XGBoost model
│   ├── score_all_students.py   # Score the full roster -> student_risk_scores.csv
│   ├── dashboard.py            # Terminal dashboard (Student/Faculty/Admin)
│   ├── test_xgboost_model.py   # Reload & evaluate the saved XGBoost model
│   └── generate_dashboard_preview.py # Build frontend dashboard_preview.html
├── backend/                    # Flask API server
├── frontend/                   # Web dashboard
│   ├── index.html              # Single-page dashboard
│   ├── dashboard_preview.html  # Self-contained HTML preview (generated)
│   ├── css/style.css
│   └── js/app.js
├── dataset/                    # All dataset files
│   ├── raw/                    # Raw source datasets
│   │   └── student_dropout_dataset_v3.csv
│   └── processed/              # Preprocessed splits + scored roster
│       ├── train.csv / val.csv / test.csv
│       └── student_risk_scores.csv
├── config/
│   └── config.yaml             # Pipeline configuration
├── models/                     # Trained models & artifacts
│   ├── dropout_model.pkl       # Config pipeline model
│   ├── preprocessor.pkl
│   ├── metrics.json
│   ├── xgboost_dropout_model.json
│   └── preprocessor.joblib
├── run_preprocessing.py        # Entry point: preprocessing
├── run_training.py             # Entry point: training
└── requirements.txt            # Python dependencies
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Web Dashboard

```bash
python backend/app.py
```

Open **http://localhost:5000** in your browser.

### 3. (Optional) Retrain the Model

If you want to retrain the model from scratch:

```bash
# Run the full pipeline (preprocessing + training)
python src/pipeline.py

# Or run steps individually
python run_preprocessing.py
python run_training.py
```

## Dashboard Features

### Student View
- **Quick Lookup**: Enter your Student ID to check your risk score
- **Manual Entry**: Input your details for a live prediction
- **Recommendations**: Get personalized suggestions based on your profile

### Faculty View
- **Department Filter**: View at-risk students by department
- **Year Filter**: Filter by academic year
- **Student Table**: Top 25 at-risk students sorted by risk probability

### Admin View
- **Overview Stats**: Total students, dropout rate, risk distribution
- **Department Analysis**: Average risk by department
- **Year Analysis**: Risk trends across academic years
- **Model Performance**: Accuracy, precision, recall, ROC-AUC metrics

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/student/<id>` | GET | Get student risk score |
| `/api/predict` | POST | Predict risk for custom profile |
| `/api/overview` | GET | Admin overview statistics |
| `/api/faculty/<dept>` | GET | Get at-risk students by department |
| `/api/departments` | GET | List available departments |
| `/api/semesters` | GET | List available semesters |

### Example API Usage

```bash
# Get student risk score
curl http://localhost:5000/api/student/42

# Predict risk for custom profile
curl -X POST http://localhost:5000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"GPA": 2.5, "Attendance_Rate": 70, "Stress_Index": 8}'

# Get admin overview
curl http://localhost:5000/api/overview
```

## Model Performance

On the held-out test set (v3 dataset, 10,000 students):

| Metric | Value |
|--------|-------|
| Accuracy | 81% |
| Dropout Precision | 62% |
| Dropout Recall | 48% (baseline) / 75%+ (tuned) |
| ROC-AUC | 0.807 |

The model uses a tuned threshold of **0.243** for the "Medium" risk cutoff, optimizing for recall to catch more at-risk students.

## Configuration

Edit `config/config.yaml` to adjust:

- **Model type**: `random_forest`, `gradient_boosting`, `logistic_regression`, or `xgboost`
- **Features**: Numerical and categorical feature lists
- **Preprocessing**: Imputation strategy, scaler type
- **Split ratios**: Train/val/test proportions

## Terminal Dashboard & XGBoost Pipeline

A terminal dashboard and a standalone XGBoost training path are included in `src/`:

```bash
# Train/tune the XGBoost model (produces models/xgboost_dropout_model.json)
python src/train_xgboost.py --dataset v3
# Add --tune for a slower hyperparameter search

# Score the full 10,000-student roster
python src/score_all_students.py

# Open the terminal dashboard (Student / Faculty / Admin)
python src/dashboard.py

# Sanity-check the saved model
python src/test_xgboost_model.py

# Build the self-contained HTML preview
python src/generate_dashboard_preview.py
```

## Data

- **student_dropout_dataset_v3.csv**: 10,000 students with explicit dropout labels
- **student_data.csv**: UCI-style dataset (395 students) for comparison

## License

MIT
