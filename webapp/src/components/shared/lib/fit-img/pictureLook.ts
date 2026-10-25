/**
 * How a small achievement picture is drawn (owner, 2026-10-12), the same rule
 * the posts sent to Telegram follow (`services/post_picture.py`): a picture
 * under `lowRes` on its longer side is not stretched over the block — it is
 * enlarged `scale` times, never past 90% of the block, and set in its middle
 * on a ground of its own colours. A larger one fills the block as before.
 *
 * The server's numbers come with `/me` (`setPictureLook`); these are only what
 * is used until it has answered.
 */
export type PictureLook = { on: boolean; scale: number; lowRes: number };

let look: PictureLook = { on: true, scale: 4, lowRes: 200 };

export function setPictureLook(next: Partial<PictureLook> | null | undefined): void {
  if (!next) return;
  look = { ...look, ...next };
}

export function pictureLook(): PictureLook {
  return look;
}

/** Whether a picture of this size is drawn small, on its ground. */
export function isSmallPicture(width: number, height: number): boolean {
  if (!look.on || width <= 0 || height <= 0) return false;
  return Math.max(width, height) < look.lowRes;
}
