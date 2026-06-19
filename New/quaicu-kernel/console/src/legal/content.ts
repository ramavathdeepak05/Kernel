// Legal document content (TEMPLATES). These are starting drafts — NOT legal advice. Replace the
// [PLACEHOLDERS] with your real details and have a qualified lawyer review before relying on them.
// Contact for all docs: support@quaicu.org.

export interface LegalDoc {
  slug: string;
  title: string;
  updated: string;
  sections: { heading: string; paras: string[] }[];
}

const ENTITY = "[Legal Entity Name]";
const ADDRESS = "[Registered Address]";
const JURISDICTION = "[City, State], India";
const UPDATED = "2026-06-19";

export const LEGAL_DOCS: LegalDoc[] = [
  {
    slug: "terms",
    title: "Terms of Service",
    updated: UPDATED,
    sections: [
      {
        heading: "1. Agreement",
        paras: [
          `These Terms govern your use of the QUAICU governance platform and console (the "Service"), operated by ${ENTITY} ("we", "us"). By creating an account or using the Service you agree to these Terms.`,
        ],
      },
      {
        heading: "2. The Service",
        paras: [
          "QUAICU provides AI/decision governance — policy evaluation, an append-only audit ledger, human-in-the-loop approvals, and related APIs. The Service is provided on a subscription/fee basis as described on our plans page.",
        ],
      },
      {
        heading: "3. Accounts & security",
        paras: [
          "You must provide accurate signup details and a valid company email. You are responsible for safeguarding your password and API keys and for all activity under your account. Notify us immediately of any unauthorised use.",
        ],
      },
      {
        heading: "4. Fees & payment",
        paras: [
          "The Starter plan carries an annual fee of ₹10,000, payable at signup and on each renewal. Business and Enterprise are quote-based and require a ₹50,000 consultation deposit to engage our integrations team. All amounts are exclusive of applicable taxes (e.g. GST). Payments are processed by Razorpay; by paying you also agree to Razorpay's terms.",
          "Fees are charged in advance and, except as stated in our Refund & Cancellation Policy or required by law, are non-refundable.",
        ],
      },
      {
        heading: "5. Acceptable use",
        paras: [
          "You will not misuse the Service, attempt to breach its security or tenant isolation, reverse-engineer it, or use it to violate any law or third-party right. We may suspend accounts that violate these Terms.",
        ],
      },
      {
        heading: "6. Intellectual property",
        paras: [
          "The Service, including its software and content, is owned by us and our licensors. You retain ownership of the data you submit; you grant us a limited licence to process it to provide the Service.",
        ],
      },
      {
        heading: "7. Disclaimers & liability",
        paras: [
          'The Service is provided "as is" without warranties of any kind. To the maximum extent permitted by law, our aggregate liability arising out of or relating to the Service is limited to the fees you paid in the 12 months preceding the claim. We are not liable for indirect or consequential losses.',
        ],
      },
      {
        heading: "8. Termination",
        paras: [
          "You may stop using the Service at any time. We may suspend or terminate access for breach of these Terms. On termination, your right to use the Service ends; certain provisions survive.",
        ],
      },
      {
        heading: "9. Governing law",
        paras: [
          `These Terms are governed by the laws of India, and the courts at ${JURISDICTION} have exclusive jurisdiction.`,
        ],
      },
      {
        heading: "10. Contact",
        paras: [`Questions about these Terms: support@quaicu.org · ${ENTITY}, ${ADDRESS}.`],
      },
    ],
  },
  {
    slug: "privacy",
    title: "Privacy Policy",
    updated: UPDATED,
    sections: [
      {
        heading: "1. Who we are",
        paras: [
          `${ENTITY} ("we") operates QUAICU. This policy explains how we handle personal data, consistent with India's Digital Personal Data Protection Act (DPDP) and, where applicable, the GDPR.`,
        ],
      },
      {
        heading: "2. Data we collect",
        paras: [
          "At signup: your name, company email, company name, job title, phone, and onboarding survey responses (industry, company size, use case, regulations of interest). For login: a password (stored only as a salted hash). Payment is handled by Razorpay — we receive a payment reference, not your card details.",
          "In use: the governance data your tenant submits to the API, audit-ledger entries, and standard request logs.",
        ],
      },
      {
        heading: "3. How we use it",
        paras: [
          "To provide and secure the Service, authenticate you, process payments, contact you about your account, and meet legal obligations. We do not sell your personal data.",
        ],
      },
      {
        heading: "4. Processors we use",
        paras: [
          "Razorpay (payments), Resend (transactional email), and Google Cloud (hosting/infrastructure). These process data on our behalf under their terms.",
        ],
      },
      {
        heading: "5. Your rights",
        paras: [
          "Subject to applicable law, you may request access, correction, or erasure of your personal data, and withdraw consent. Contact support@quaicu.org. Tenant data deletion follows our data-retention and crypto-shredding practices.",
        ],
      },
      {
        heading: "6. Retention & security",
        paras: [
          "We retain personal data for as long as your account is active and as required by law, then delete or anonymise it. We apply tenant isolation, encryption in transit, and access controls.",
        ],
      },
      {
        heading: "7. Contact",
        paras: [`Privacy questions / requests: support@quaicu.org · ${ENTITY}, ${ADDRESS}.`],
      },
    ],
  },
  {
    slug: "refunds",
    title: "Refund & Cancellation Policy",
    updated: UPDATED,
    sections: [
      {
        heading: "1. Starter annual fee (₹10,000)",
        paras: [
          "The ₹10,000 annual Starter fee is charged at signup and activates your workspace immediately. Because access is granted on payment, this fee is non-refundable once the workspace is provisioned, except where a refund is required by law.",
          "You may cancel anytime to stop future renewals; cancellation prevents the next annual charge but does not refund the current period.",
        ],
      },
      {
        heading: "2. Business / Enterprise consultation deposit (₹50,000)",
        paras: [
          "The ₹50,000 consultation deposit secures engagement with our integrations team and is non-refundable, as it reserves dedicated team time. Where you proceed to a paid plan, we may, at our discretion, adjust the deposit against your first invoice.",
        ],
      },
      {
        heading: "3. How to cancel or request a refund",
        paras: [
          "Email support@quaicu.org with your account email and request. Approved refunds (where applicable) are returned to the original payment method via Razorpay within standard processing timelines.",
        ],
      },
      {
        heading: "4. Contact",
        paras: ["support@quaicu.org"],
      },
    ],
  },
  {
    slug: "contact",
    title: "Contact Us",
    updated: UPDATED,
    sections: [
      {
        heading: "Get in touch",
        paras: [
          "Support & general enquiries: support@quaicu.org",
          "Business / Enterprise / integrations: start a consultation from the plans page, or email support@quaicu.org.",
        ],
      },
      {
        heading: "Company",
        paras: [`${ENTITY}`, `${ADDRESS}`],
      },
    ],
  },
];

export const LEGAL_BY_SLUG: Record<string, LegalDoc> = Object.fromEntries(
  LEGAL_DOCS.map((d) => [d.slug, d]),
);
