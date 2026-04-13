"""
P14 — External Integrations for Admissions Workflow.

Available integrations:
  - DigiLockerClient        — Academic certificate verification (India)
  - EmailProvisionClient    — Google Workspace / Microsoft 365 email provisioning
  - LMSSyncClient           — Moodle LMS account sync
  - NTAScoreImporter        — NTA/CUET score file import
  - PaymentGatewayClient    — Razorpay / PayU fee collection
  - SMSGatewayClient        — MSG91 / Twilio OTP + notifications
  - DocumentStorageClient   — AWS S3 / Azure Blob / local file storage
"""

from __future__ import annotations
