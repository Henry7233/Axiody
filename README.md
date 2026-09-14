Creating a new branch in git
=============================
git checkout -b [branch name]
git branch
git checkout [branch name] #swap the branches
git branch -d [branch name] #**done only after merging and pulling

On Your Computer
================
git status
git add .
git commit -m "Description"

Remote Repository
==================
git push -u origin [branch name]
git pull

Admin dashboard data
====================
The admin dashboard at `/admin/dashboard` reads `users.db` through
`Config.DATABASE`. Refresh the page after uploads or validation updates.

- Each row in `documents` counts as one submitted file.
- `validation_status = Complete` counts as Bookkept; incomplete and pending
  validation records count as Under Review. This is a validation-based summary,
  not a separate accounting approval status.
- The reporting filter uses `document_date`, while submission tables show
  `created_at`. All dates is the default, and stored reporting months are selectable.
- Document types use `document_type`, then `ai_document_type`, falling back to Other.
- Clients counts all client accounts in `users`; names are joined by `documents.user_id`.
- The dashboard shows the five latest submissions and attention records. View all
  retains the selected reporting period and displays all matching records.
- Deadlines use active saved notifications and the existing reminder deadline rule.
  Loading the dashboard does not send reminders.

Run the dashboard regression checks from the Axiody directory:
`python -m unittest discover -s tests -v`
