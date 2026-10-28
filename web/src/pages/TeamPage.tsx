import { useCallback, useEffect, useState } from "react";
import { Check, Copy, MailPlus, Users } from "lucide-react";
import { api, shortDate } from "../api";
import type { Organization } from "../types";
import { Button, EmptyState, Field, PageHeader } from "../ui";

type Member = { user_id: string; email: string; role: string; active: boolean };
type Invitation = { email: string; role: string; expires_at: string; acceptance_token: string };

const roleLabels: Record<string, string> = {
  admin: "Administrator",
  warehouse_manager: "Warehouse manager",
  salesperson: "Salesperson",
};

export function TeamPage({ token, organization }: { token: string; organization: Organization }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [form, setForm] = useState({ email: "", role: "salesperson" });
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await api<{ items: Member[] }>(`/organizations/${organization.id}/members`, {}, token);
      setMembers(result.items);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load team.");
    }
  }, [organization.id, token]);

  useEffect(() => { void load(); }, [load]);

  async function invite(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError(""); setInvitation(null);
    try {
      setInvitation(await api<Invitation>(`/organizations/${organization.id}/invitations`, { method: "POST", body: JSON.stringify(form) }, token));
      setForm({ ...form, email: "" });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not create invitation.");
    } finally { setLoading(false); }
  }

  async function copyToken() {
    if (!invitation) return;
    await navigator.clipboard.writeText(invitation.acceptance_token);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return <>
    <PageHeader title="Team" description="Control who can operate this organization and what role they receive." />
    <section className="team-layout">
      <div className="section-block">
        <div className="section-heading"><div><h2>Members</h2><p>Active identities with access to this business.</p></div><Users /></div>
        {members.length === 0 ? <EmptyState>No members found.</EmptyState> : <div className="member-list">{members.map((member) => <div key={member.user_id}><span><strong>{member.email}</strong><small>{roleLabels[member.role] ?? member.role}</small></span><span className={`status ${member.active ? "success" : "neutral"}`}>{member.active ? "Active" : "Inactive"}</span></div>)}</div>}
      </div>
      <div className="section-block">
        <div className="section-heading"><div><h2>Invite teammate</h2><p>The invitation expires after 24 hours and can be used once.</p></div><MailPlus /></div>
        <form className="invite-form" onSubmit={invite}><Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></Field><Field label="Role"><select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="salesperson">Salesperson</option><option value="warehouse_manager">Warehouse manager</option><option value="admin">Administrator</option></select></Field><Button type="submit" loading={loading}>Create invitation</Button></form>
        {error && <div className="form-error">{error}</div>}
        {invitation && <div className="invitation-result"><span>Invitation created for <strong>{invitation.email}</strong></span><small>Expires {shortDate(invitation.expires_at)}. Share this secret token through a trusted channel.</small><code>{invitation.acceptance_token}</code><Button variant="secondary" onClick={copyToken}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? "Copied" : "Copy token"}</Button></div>}
      </div>
    </section>
  </>;
}
