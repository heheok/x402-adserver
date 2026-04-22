import { usePrivy } from "@privy-io/react-auth";

import Login from "./pages/Login";
import Home from "./pages/Home";

export default function App() {
  const { ready, authenticated } = usePrivy();

  if (!ready) {
    return (
      <main className="centered">
        <p>Loading…</p>
      </main>
    );
  }

  return authenticated ? <Home /> : <Login />;
}
