import { usePrivy } from "@privy-io/react-auth";

export default function Login() {
  const { login } = usePrivy();

  return (
    <main className="centered">
      <div className="card">
        <h1>Advertiser Dashboard</h1>
        <p className="muted">Sign in to manage your campaigns.</p>
        <button onClick={login}>Sign in with email</button>
        <p className="footnote">
          Demo — simulates a third-party ad-tech platform integrating with the
          x402 Ad Server API.
        </p>
      </div>
    </main>
  );
}
