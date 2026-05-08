import axios from "axios";

const base = import.meta.env.VITE_API_BASE_URL || "";

export async function login(email: string, password: string) {
  const res = await axios.post(`${base}/auth/login`, { email, password });
  return res.data as { access_token: string; refresh_token: string };
}

export async function register(email: string, password: string, name: string) {
  const res = await axios.post(`${base}/auth/register`, { email, password, name });
  return res.data;
}
