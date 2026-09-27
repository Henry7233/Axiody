# AXIODY

AXIODY is a Flask bookkeeping document submission and review application. Clients submit accounting documents, while administrators review classifications, approve or reject submissions, manage clients, and download bookkeeping records.

## Features

- Client registration, login, logout, password reset, and OTP verification.
- Client dashboard with document history, notifications, settings, and reminders.
- PDF-only client document submissions. PNG, JPG, Word, Excel, CSV, and text files are rejected.
- AI classification into `Invoice`, `Receipt`, `Bank Statement`, or `Other`.
- AI validation for document completeness and bookkeeping-related issues.
- Local fallback checks when the configured AI provider is unavailable or returns an invalid response.
- Admin approval and rejection workflow with email notifications.
- Gmail SMTP notifications for password reset, account updates, document decisions, and reminders.
- Incomplete-document reminders tracked in SQLite and scheduled every five days until the monthly deadline.
- Bookkeeping views and downloads for reviewed documents.
- Token usage logging when `DEBUG_LLM` is enabled.

## Requirements

- Python 3.10 or newer
- A virtual environment is recommended.
- Either a compatible LLM gateway or AWS Bedrock credentials.

## Installation

From the project directory:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment Configuration

Create a `.env` file in the project root. Never commit this file because it contains credentials.

```dotenv
SECRET_KEY=replace-with-a-long-random-secret

# LLM gateway option
LLM_GATEWAY_URL=https://your-gateway.example
LLM_GATEWAY_API_KEY=replace-with-your-api-key
LLM_MODEL=your-model-id
DEBUG_LLM=0
```

## Running the Application

Start the development server from the project root:

```powershell
python app.py
```

For Flask CLI commands, set the application and run:

```powershell
$env:FLASK_APP = "app.py"
flask process-reminders
```

The reminder command processes incomplete documents that are due for another notification.

## Main Workflows

### Client

1. Register or sign in.
2. Open the upload page and provide a title, document date, and optional description.
3. Upload one or more PDF files.
4. AXIODY extracts PDF text, classifies the document, validates it, and stores the result.
5. Review notifications and resubmit corrected documents when requested.

### Administrator

1. Sign in with an administrator account.
2. Use the dashboard to monitor submissions and client activity.
3. Review documents awaiting approval, including the AI classification and confidence.
4. Approve or reject documents and provide feedback when needed.
5. Use Bookkeeping to view or download processed records.

## AI Agents

The agents are in `app/agents/`:

- `classification_agent.py` identifies invoices, receipts, bank statements, and other documents.
- `validation_agent.py` checks document quality, required information, and dates.
- `reminder_agent.py` creates and processes incomplete-document reminders.

The shared LLM integration is in `app/services/ai_service.py`. It accepts JSON responses, including responses wrapped in Markdown code fences or surrounded by additional text. If an AI request fails, the application logs a safe warning and uses local fallback checks.

To print provider token usage in the terminal during gateway requests:

```dotenv
DEBUG_LLM=1
```

Token counts are printed for prompt, completion, and total usage. Request contents, credentials, and provider response bodies are not logged.

## Email Notifications

Email delivery is centralized in `app/services/email_servie.py` and is used for:

- Password reset OTPs
- Account update OTPs
- Admin approval and rejection decisions
- Incomplete-document reminders

The application records reminder notifications even when SMTP delivery fails, and logs the delivery error for diagnosis. Check SMTP credentials, Gmail App Password configuration, firewall rules, and network access when email cannot be delivered.

## Project Layout

```text
app.py                         Flask entry point
config.py                      Environment and application configuration
requirements.txt               Python dependencies
app/
	agents/                      Classification, validation, and reminder agents
	models/                      SQLite persistence and data access
	routes/                      Authentication, client, and admin routes
	services/                    AI, email, file, and bookkeeping services
	static/                      CSS, JavaScript, and images
	templates/                   Jinja templates for auth, client, and admin pages
prompts/                       Agent prompt files
users.db                      Local SQLite database, created at runtime
```

## Security Notes

- Keep `.env`, `users.db`, and API credentials out of source control.
- Use a strong production `SECRET_KEY`.
- Use HTTPS in production.-
- Set `DEBUG_LLM=0` in production unless token usage diagnostics are specifically required.
- The built-in Flask server is intended for local development, not production hosting.