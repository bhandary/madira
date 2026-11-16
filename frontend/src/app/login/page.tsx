import { LoginPanel } from "@/app/login/login-panel";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const query = await searchParams;
  const raw = Array.isArray(query.error) ? query.error[0] : query.error;
  const error = raw && /^[a-z_]{1,32}$/.test(raw) ? raw : raw ? "server" : "";

  return (
    <div data-testid="login-page" className="login-hero max-w-md">
      <div className="wave-accent" aria-hidden="true" />
      <div className="login-card">
        <p className="kicker">Account</p>
        <h1 className="mt-2 h-page">Sign in</h1>
        <p className="lead">
          Use a Google account. Menus, lists, inventory, and the sommelier stay available if you skip this.
        </p>
        <LoginPanel error={error} />
      </div>
    </div>
  );
}
