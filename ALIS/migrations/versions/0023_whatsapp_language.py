"""WhatsApp Business API language variants + delivery log

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-16

Changes
───────
1. users.preferred_language  — VARCHAR(5) NOT NULL DEFAULT 'en'
   Supported values: en | te | kn | ta | mr | hi
   Used by WhatsAppService to select the correct MSG91 template variant.

2. notification_templates enhancements:
   - language             VARCHAR(5) NOT NULL DEFAULT 'en'
   - whatsapp_template_id VARCHAR(200)        — MSG91 pre-registered template ID
   - channel              VARCHAR(20) NOT NULL DEFAULT 'EMAIL'
                            (EMAIL | WHATSAPP | SMS | IN_APP)
   - UNIQUE index: (org_id, template_name, language, channel)
     Prevents duplicate template registrations per language+channel pair.

3. whatsapp_delivery_log — idempotency store for MSG91 outbound messages
   - msg_ref_id  UNIQUE — MSG91's message reference ID prevents double-send
   - status lifecycle: QUEUED → SENT → DELIVERED | FAILED | OPT_OUT
   - Delivery webhook updates delivered_at or failed_reason
"""

from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Preferred language on users
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(5) NOT NULL DEFAULT 'en';
    """)

    # 2. Language + WhatsApp fields on notification_templates
    op.execute("""
        ALTER TABLE notification_templates
            ADD COLUMN IF NOT EXISTS language VARCHAR(5) NOT NULL DEFAULT 'en',
            ADD COLUMN IF NOT EXISTS whatsapp_template_id VARCHAR(200),
            ADD COLUMN IF NOT EXISTS channel VARCHAR(20) NOT NULL DEFAULT 'EMAIL';
    """)

    # Unique constraint: one template entry per org + name + language + channel
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_template_name_lang_channel
            ON notification_templates(org_id, template_name, language, channel);
    """)

    # 3. WhatsApp delivery log
    op.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_delivery_log (
            id              BIGSERIAL PRIMARY KEY,
            org_id          UUID NOT NULL,
            msg_ref_id      VARCHAR(200),
            recipient_phone VARCHAR(20) NOT NULL,
            template_name   VARCHAR(100) NOT NULL,
            language        VARCHAR(5) NOT NULL DEFAULT 'en',
            variables       JSONB,
            status          VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
            sent_at         TIMESTAMPTZ,
            delivered_at    TIMESTAMPTZ,
            failed_reason   TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_whatsapp_msg_ref UNIQUE (msg_ref_id)
        );

        CREATE INDEX IF NOT EXISTS idx_wa_log_recipient
            ON whatsapp_delivery_log(recipient_phone, created_at);

        CREATE INDEX IF NOT EXISTS idx_wa_log_status
            ON whatsapp_delivery_log(status, created_at);

        CREATE INDEX IF NOT EXISTS idx_wa_log_org
            ON whatsapp_delivery_log(org_id, template_name);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS whatsapp_delivery_log;")
    op.execute("""
        DROP INDEX IF EXISTS uq_template_name_lang_channel;
        ALTER TABLE notification_templates
            DROP COLUMN IF EXISTS language,
            DROP COLUMN IF EXISTS whatsapp_template_id,
            DROP COLUMN IF EXISTS channel;
        ALTER TABLE users
            DROP COLUMN IF EXISTS preferred_language;
    """)
