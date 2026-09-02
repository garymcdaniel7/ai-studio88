import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — AI Studio",
  description: "How AI Studio collects, uses, and protects your data.",
};

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight">Privacy Policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Last updated: September 2, 2026
      </p>

      <div className="mt-8 space-y-6 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">1. Overview</h2>
          <p>
            AI Studio ("we", "us", "our") provides an AI content production
            platform for brands and content creators. This Privacy Policy
            explains what information we collect, why we collect it, and how
            it is used and protected.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">2. Information We Collect</h2>
          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>Account information:</strong> email address, display
              name, and authentication identifiers when you create an account
              or sign in.
            </li>
            <li>
              <strong>Content you create:</strong> prompts, generated media,
              project files, and asset metadata you upload or produce.
            </li>
            <li>
              <strong>Usage data:</strong> pages visited, features used, and
              generation activity to operate and improve the service.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">3. How We Use Information</h2>
          <ul className="list-disc pl-6 space-y-2">
            <li>Provide, maintain, and secure the platform.</li>
            <li>Process generation jobs and store your assets.</li>
            <li>Monitor performance and diagnose technical issues.</li>
            <li>Comply with legal obligations.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">4. Third-Party Services</h2>
          <p>
            AI Studio uses third-party infrastructure to operate, including
            cloud hosting, database, storage, and GPU compute providers. These
            providers process data solely to deliver the service. We do not
            sell your personal information.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">5. Data Retention</h2>
          <p>
            We retain your data while your account is active and as long as
            needed to provide the service or satisfy legal obligations. You may
            request deletion of your account and associated data at any time.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">6. Your Rights</h2>
          <p>
            Depending on your jurisdiction, you may have the right to access,
            correct, export, or delete your personal data. To exercise these
            rights, contact us at the address below.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">7. Contact</h2>
          <p>
            Questions about this policy:{" "}
            <a href="mailto:helloglamourgirl@gmail.com" className="underline">
              helloglamourgirl@gmail.com
            </a>
          </p>
        </section>
      </div>
    </main>
  );
}
