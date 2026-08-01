import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";

/**
 * Fetches GET /api/v1/users/{userId}/profile. Distinguishes "no profile
 * exists for this user_id" (404 — a real, expected outcome for a user who's
 * never sent a login event, not a failure) from a genuine network/HTTP
 * error, so the page can render each case with the right message rather
 * than treating both as the same generic error state.
 */
export function useUserProfile(userId) {
  const [profile, setProfile] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!userId) {
      setProfile(null);
      setNotFound(false);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setNotFound(false);
    setError(null);

    async function fetchProfile() {
      try {
        const res = await fetch(`${API_URL}/api/v1/users/${encodeURIComponent(userId)}/profile`);
        if (res.status === 404) {
          if (active) {
            setProfile(null);
            setNotFound(true);
          }
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (active) setProfile(data);
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }

    fetchProfile();
    return () => {
      active = false;
    };
  }, [userId]);

  return { profile, notFound, loading, error };
}
