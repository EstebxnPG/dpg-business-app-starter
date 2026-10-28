import { useState } from "react";
import { ArrowRight, Building2, LockKeyhole, Mail } from "lucide-react";
import { api } from "../api";
import { Button, Field } from "../ui";

export function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api<{ access_token: string }>("/auth/token", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      onLogin(result.access_token);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not sign in.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-context">
        <div className="login-brand"><Building2 size={24} /><span>DPG Business</span></div>
        <div>
          <p className="eyebrow">Operations workspace</p>
          <h1>Control what moves through your business.</h1>
          <p>Inventory, sales, discounts and returns in one traceable workflow.</p>
        </div>
        <div className="login-signal">
          <span>Reliable by design</span>
          <strong>Every stock change keeps its reason and actor.</strong>
        </div>
      </section>
      <section className="login-panel">
        <form onSubmit={submit}>
          <div className="form-heading"><h2>Sign in</h2><p>Use your business account to continue.</p></div>
          <Field label="Email">
            <div className="input-with-icon"><Mail size={17} /><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required /></div>
          </Field>
          <Field label="Password">
            <div className="input-with-icon"><LockKeyhole size={17} /><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" minLength={8} required /></div>
          </Field>
          {error && <div className="form-error">{error}</div>}
          <Button type="submit" loading={loading}>Continue <ArrowRight size={17} /></Button>
        </form>
      </section>
    </main>
  );
}
