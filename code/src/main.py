import imaplib
import email
from email.header import decode_header
import hashlib
import json
import openai
import os
from pdfminer.high_level import extract_text

# Email configuration
IMAP_SERVER = "imap.yourmailserver.com"
EMAIL_ACCOUNT = "your_email@example.com"
EMAIL_PASSWORD = "your_password"
FOLDER = "INBOX"

# OpenAI API configuration
OPENAI_API_KEY = "your_openai_api_key"
openai.api_key = OPENAI_API_KEY

# Dictionary to track processed emails (to avoid duplicates)
processed_emails = set()

# Mapping of request types and sub-request types
REQUEST_MAPPING = {
    "Adjustment": ["Reallocation Fees", "Amendment Fees", "Reallocation Principal"],
    "AU Transfer": [],
    "Closing Notice": ["Cashless Roll", "Decrease", "Increase"],
    "Commitment Change": [],
    "Fee Payment": ["Ongoing Fee", "Letter of Credit Fee", "Principal", "Interest", "Principal + Interest", "Principal+Interest+Fee"],
    "Money Movement-Inbound": [],
    "Money Movement - Outbound": ["Timebound", "Foreign Currency"]
}

# Mapping request types to teams
TEAM_MAPPING = {
    "Adjustment": "Finance Team",
    "AU Transfer": "Finance Team",
    "Closing Notice": "Legal Team",
    "Commitment Change": "Finance Team",
    "Fee Payment": "Finance Team",
    "Money Movement-Inbound": "Accounts Team",
    "Money Movement - Outbound": "Accounts Team",
}

def hash_email_content(content):
    """Generate a hash of the email content to track duplicates."""
    return hashlib.md5(content.encode()).hexdigest()

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    return extract_text(pdf_path)

def extract_intent_using_openai(content):
    """Use OpenAI to extract the request type, sub-request type, and key attributes from the content."""
    prompt = f"""
    Extract the request type and sub-request type from the following content. 
    Match against the predefined request types and sub-request types:
    {REQUEST_MAPPING}
    Content:
    """
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are an AI that extracts service request details from emails."},
                  {"role": "user", "content": prompt}]
    )
    
    return json.loads(response["choices"][0]["message"]["content"].strip())

def assign_team(request_type):
    """Assign the request to the appropriate team."""
    return TEAM_MAPPING.get(request_type, "General Support Team")

def fetch_emails():
    """Fetch and process emails."""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
    mail.select(FOLDER)

    status, messages = mail.search(None, 'UNSEEN')  # Fetch unread emails
    if status != "OK":
        print("No new emails found.")
        return
    
    for num in messages[0].split():
        status, data = mail.fetch(num, "(RFC822)")
        if status != "OK":
            continue
        
        msg = email.message_from_bytes(data[0][1])
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")
        
        sender = msg["From"]
        
        body = ""
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break  # If email body is found, no need to check attachments
                elif content_type == "application/pdf":
                    filename = part.get_filename()
                    if filename:
                        filepath = os.path.join("/tmp", filename)
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        attachments.append(filepath)
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        
        if not body and attachments:
            # If no body, extract text from the first PDF attachment
            body = extract_text_from_pdf(attachments[0])
        
        email_hash = hash_email_content(body)
        if email_hash in processed_emails:
            print("Skipping duplicate email.")
            continue
        
        processed_emails.add(email_hash)
        intent_data = extract_intent_using_openai(body)
        team = assign_team(intent_data["Request Type"])
        
        request_data = {
            "Subject": subject,
            "Sender": sender,Q
            "Request Type": intent_data["Request Type"],
            "Sub Request Type": intent_data["Sub Request Type"],
            "Attributes": intent_data["Attributes"],
            "Assigned Team": team
        }
        print(json.dumps(request_data, indent=4))
    
    mail.logout()

if __name__ == "__main__":
    fetch_emails()
