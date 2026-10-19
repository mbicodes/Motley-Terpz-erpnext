"""TSBC Farm and Nursery Daily Reports.

Two submittable DocTypes (Farm Daily Report, Nursery Daily Report) filled once a day
from the Web Pages /farm-daily-report and /nursery-daily-report, emailed to the
Daily Report Recipient role on submit, with a reminder at 3 PM farm time when the
day's report is missing.

	rules.py    server-side validation shared by both DocType controllers
	api.py      FLC supplier list for the page, the reminder job
	install.py  after_migrate: masters, settings defaults, notifications, web pages
	web/        page sources (one CSS, one engine, one config per page)
"""
