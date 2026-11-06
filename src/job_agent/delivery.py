"""Build a downloadable draft email; no sending transport is included."""

from .i18n import tr
from email.message import EmailMessage
from email.utils import make_msgid

from .store import artifact




def build_email(job, root, sender):
    dossier = job['dossier']
    plan = dossier['submission']
    recipient = plan['recipient']
    if '\n' in recipient or '\r' in recipient or '@' not in recipient:
        raise ValueError(tr('delivery.invalid_reviewed_recipient'))
    message = EmailMessage()
    message['From'], message['To'] = sender, recipient
    message['Subject'] = dossier['answers'].get('subject', job['role'])
    message['Message-ID'] = make_msgid()
    message.set_content(dossier['answers'].get('body', dossier.get('motivation', '')))
    for attachment in dossier['attachments']:
        if attachment.get('send', True):
            path = artifact(root, attachment['path'])
            if path.suffix != '.pdf': raise ValueError(tr('delivery.email_attachments_must_be_reviewed_pdf_files'))
            message.add_attachment(path.read_bytes(),maintype='application',subtype='pdf',filename=path.name)
    return message
