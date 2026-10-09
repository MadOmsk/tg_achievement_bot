/** Passkeys in the browser (owner, 2026-10-08): the server's options in, the
 * phone's answer out, both as JSON — WebAuthn itself speaks in byte buffers. */

type Json = Record<string, unknown>;

function toBytes(text: string): ArrayBuffer {
  const base64 = text.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toText(buffer: ArrayBuffer | null): string | null {
  if (!buffer) return null;
  let binary = "";
  for (const byte of new Uint8Array(buffer)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] {
  return Array.isArray(list)
    ? list.map((item: Json) => ({
        type: "public-key",
        id: toBytes(String(item.id)),
        transports: item.transports as AuthenticatorTransport[] | undefined,
      }))
    : [];
}

/** Whether this browser can make and use a passkey at all. Inside Telegram the
 * app signs in with Telegram, and its in-app browser often cannot. */
export function passkeysSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "PublicKeyCredential" in window &&
    typeof navigator.credentials?.create === "function" &&
    !window.Telegram?.WebApp?.initData
  );
}

/** The person stepped back from the phone's prompt (or it timed out): nothing
 * went wrong, nothing to say. */
export function passkeyCancelled(err: unknown): boolean {
  return err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "AbortError");
}

export async function createPasskey(options: Json): Promise<Json> {
  const user = options.user as Json;
  const credential = (await navigator.credentials.create({
    publicKey: {
      ...(options as unknown as PublicKeyCredentialCreationOptions),
      challenge: toBytes(String(options.challenge)),
      user: { ...(user as unknown as PublicKeyCredentialUserEntity), id: toBytes(String(user.id)) },
      excludeCredentials: descriptors(options.excludeCredentials),
    },
  })) as PublicKeyCredential;
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toText(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toText(response.clientDataJSON),
      attestationObject: toText(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : [],
    },
  };
}

export async function getPasskey(options: Json): Promise<Json> {
  const credential = (await navigator.credentials.get({
    publicKey: {
      ...(options as unknown as PublicKeyCredentialRequestOptions),
      challenge: toBytes(String(options.challenge)),
      allowCredentials: descriptors(options.allowCredentials),
    },
  })) as PublicKeyCredential;
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toText(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toText(response.clientDataJSON),
      authenticatorData: toText(response.authenticatorData),
      signature: toText(response.signature),
      userHandle: toText(response.userHandle),
    },
  };
}
