/**
 * Which identity the WebSocket URL carries is a security decision.
 *
 * The backend authorizes the subscription before accepting it, and after
 * the production auth fix it only trusts `user_email` outside production.
 * If this builder sent the dev-stub address while a real session existed,
 * a logged-in user would be refused their own project's events in dev and
 * would get nothing at all in production.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { wsUrl } from "./useProjectEvents";
import { USER_EMAIL } from "./api";

describe("wsUrl", () => {
  beforeEach(() => localStorage.clear());

  it("uses the session token when one is stored", () => {
    localStorage.setItem("sur.auth", JSON.stringify({ token: "abc.def.ghi" }));
    const url = wsUrl("p1");
    expect(url).toContain("token=abc.def.ghi");
    expect(url).not.toContain("user_email");
  });

  it("falls back to the dev email only when there is no token", () => {
    const url = wsUrl("p1");
    expect(url).toContain(`user_email=${encodeURIComponent(USER_EMAIL)}`);
    expect(url).not.toContain("token=");
  });

  it("does not send a token key when the stored session has no token", () => {
    localStorage.setItem("sur.auth", JSON.stringify({ user: { id: "u1" } }));
    expect(wsUrl("p1")).toContain("user_email=");
  });

  it("survives corrupt storage instead of throwing", () => {
    localStorage.setItem("sur.auth", "not json {{{");
    expect(() => wsUrl("p1")).not.toThrow();
    expect(wsUrl("p1")).toContain("user_email=");
  });

  it("escapes the identity so a crafted value cannot add query parameters", () => {
    localStorage.setItem("sur.auth", JSON.stringify({ token: "a&admin=1" }));
    const url = wsUrl("p1");
    expect(url).toContain("token=a%26admin%3D1");
    expect(url).not.toContain("admin=1&");
  });

  it("targets ws:// derived from the http API base", () => {
    expect(wsUrl("p1")).toMatch(/^wss?:\/\//);
    expect(wsUrl("p1")).toContain("/ws/projects/p1?");
  });
});
