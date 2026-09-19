# AXIODY

AXIODY is a Flask bookkeeping document submission and review application. Clients submit accounting documents, while administrators review classifications, approve or reject submissions, manage clients, and download bookkeeping records.

Clients upload PDF accounting documents, the app extracts and validates the content, and administrators review AI-generated classification and validation checks before approving or rejecting each submission. The system also includes email OTP flows, password resets, reminder processing, and bookkeeping export workflows.

## Features

- Client registration, login, logout, and password reset
- OTP-based account and password verification
- Client and admin dashboard views
- PDF-only uploads with rejection for unsupported file types
- AI classification into invoice, receipt, bank statement, or other
- AI validation for document completeness and bookkeeping-related issues
- Local fallback checks when the LLM gateway fails or returns invalid output
- Admin approval and rejection workflow with document feedback
- Email notifications for resets, verifications, approvals, rejections, and reminders
- Reminder tracking for incomplete documents with 5-day interval using SQLite
- Bookkeeping review and export for approved records
- Optional LLM token usage logging

## Tech Stack

- Python 3.10+
- Flask 3
- SQLite
- OpenAI-compatible LLM gateway
- pypdf and openpyxl

## Prerequisites

- Python 3.10 or newer
- Virtual environment recommended
- OpenAI-compatible LLM gateway access
- SMTP credentials for email-based OTP and reminder delivery

## Installation

From the project root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root and do not commit it to source control.

```dotenv
SECRET_KEY=replace-with-a-long-random-secret

# Required: LLM gateway configuration
LLM_GATEWAY_URL=https://your-gateway.example
LLM_GATEWAY_API_KEY=replace-with-your-api-key
LLM_MODEL=your-model-id
DEBUG_LLM=0

# Optional email settings
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=1
MAIL_USE_SSL=0
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
MAIL_LOGO_URL=https://example.com/logo.png

# OTP settings
OTP_EXPIRY_MINUTES=5
OTP_MAX_ATTEMPTS=5
```

Notes:

- The app uses the LLM gateway for classification and validation.
- Gmail should use an App Password rather than the account password.
- If `DEBUG_LLM=1`, token usage is printed during LLM requests.

## Running the App

Start the development server:

```powershell
python app.py
```

Run reminder processing manually:

```powershell
$env:FLASK_APP = "app.py"
flask process-reminders
```

On macOS or Linux:

```bash
export FLASK_APP=app.py
flask process-reminders
```

This command sends overdue reminder emails and resolves completed reminder records.

## Create the First System Administrator

Public registration creates client accounts only. Before an administrator can use
the admin dashboard or create additional administrators, create the first
protected administrator from the project root:

```powershell
python
```

Then run the following Python code at the prompt, replacing the placeholder
values with the administrator's details:

```python
from getpass import getpass
from app import create_app
from app.models.users import create_user

app = create_app()
with app.app_context():
  user = create_user(
    app.config["DATABASE"],
    "admin@example.com",
    getpass("Admin password: "),
    account_type="admin",
    protected=1,
    full_name="Administrator Name",
    role="Administrator",
  )
  print("Administrator created." if user else "That email already exists.")
```

Exit Python with `exit()`, start the app, and sign in with the new administrator
account. The protected administrator can then use **Admin Management** to create
additional admin accounts. Keep the administrator password private and use a
strong password.

## Application Flow

### Client flow

1. Register or sign in.
2. Open the upload page and add document details.
3. Submit one or more PDF files.
4. The system extracts text, classifies the document, validates it, and stores the result.
5. Review notifications and resubmit corrected documents if needed.

### Admin flow

1. Sign in with an administrator account.
2. Review client activity and pending submissions.
3. Inspect AI classification and validation detail.
4. Approve or reject each document with feedback.
5. Use bookkeeping views to review or export processed records.

## Project Structure

```text
app.py                    Flask entry point
config.py                 App configuration and environment loading
requirements.txt          Python dependencies
README.md                 Project documentation
users.db                  SQLite database created at runtime
app/
  __init__.py              Flask app factory
  time.py                  Utility for Singapore time handling
  agents/
    classification_agent.py
    reminder_agent.py
    validation_agent.py
  models/
    admin_dashboard.py
    bookkeeping.py
    documents.py
    notifications.py
    users.py
  routes/
    admin.py
    auth.py
    client.py
  services/
    ai_service.py
    bookkeeping_export.py
    email_service.py
    file_service.py
  static/
    css/
    js/
    images/
  templates/
    auth/
    client/
    admin/
    base.html
prompts/
  classification_agent_prompt.txt
  reminder_agent_prompt.txt
  validation_agent_prompt.txt
```

## AI and Validation Notes

The AI logic is located in the `app/agents` package:

- `classification_agent.py` identifies invoices, receipts, bank statements, and other document types.
- `validation_agent.py` checks whether the document is complete and suitable for bookkeeping processing.
- `reminder_agent.py` handles follow-up reminder generation and delivery.

The shared LLM layer in `app/services/ai_service.py` accepts JSON returned by the model and tolerates Markdown fences and surrounding text. If a request fails, the app logs a warning and uses local fallback checks instead.

## Email and Security Notes

- Email delivery is handled in `app/services/email_service.py`.
- The app sends OTP codes, password-reset messages, approval/rejection emails, and reminder emails.
- If SMTP delivery fails, the reminder is still recorded and the error is logged.
- Keep `.env`, `users.db`, and API credentials out of version control.
- Use a strong `SECRET_KEY` in production.
- Prefer HTTPS and disable debug features in production.
- The built-in Flask development server is intended for local development only.

## Useful Commands

### Windows PowerShell

```powershell
# create a virtual environment
python -m venv venv

# activate it
.\venv\Scripts\Activate.ps1

# install dependencies
pip install -r requirements.txt

# start the app
python app.py

# process reminders manually
flask --app app.py process-reminders
```

### macOS and Linux

```bash
# create a virtual environment
python3 -m venv venv

# activate it
source venv/bin/activate

# install dependencies
python -m pip install -r requirements.txt

# start the app
python app.py

# process reminders manually
flask --app app.py process-reminders
```

This project is intended to be extended through the routes, services, models, and templates as business rules evolve.