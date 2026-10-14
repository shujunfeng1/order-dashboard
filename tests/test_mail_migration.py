import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import imaplib
import tempfile
from email.message import EmailMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import email_reader
import customer_login_email


class MailMigrationTests(unittest.TestCase):
    def test_logout_eof_does_not_discard_download(self):
        mail = Mock()
        mail.logout.side_effect = imaplib.IMAP4.abort("socket error: EOF")
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "report.xlsx"
            file.write_bytes(b"test")
            with patch.object(email_reader, "connect_mailbox", return_value=mail),                  patch.object(email_reader, "search_emails", return_value=[b"1"]),                  patch.object(email_reader, "download_attachments", return_value=[str(file)]):
                self.assertEqual(email_reader.fetch_and_download({}, folder), [str(file)])
        mail.logout.assert_called_once()

    def test_false_positive_search_never_downloads_attachment(self):
        message = EmailMessage()
        message["Subject"] = "Unrelated confidential report"
        message.set_content("test")
        message.add_attachment(b"sensitive", maintype="application",
                               subtype="octet-stream", filename="unrelated.xlsx")
        mail = Mock()
        mail.fetch.return_value = ("OK", [(b"1", message.as_bytes())])
        with tempfile.TemporaryDirectory() as folder:
            config = {"email": {"subject_filter": "Expected report", "attachment_keyword": ".xlsx"}}
            self.assertEqual(email_reader.download_attachments(mail, [b"1"], config, folder), [])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_login_leaves_single_inbox_selection_to_reader(self):
        config = {"email": {"imap_server": "example.test", "email_account": "test@example.test"}}
        with patch.dict("os.environ", {"EMAIL_PASSWORD": "test-only"}),              patch.object(customer_login_email.imaplib, "IMAP4_SSL") as ssl:
            mail = customer_login_email.connect_mailbox(config)
            mail.login.assert_called_once()
            mail.select.assert_not_called()
