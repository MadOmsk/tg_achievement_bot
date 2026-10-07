/** A nickname as shown (#157): the digits a taken name gets, `#4821`, stay with
 * it but read quieter than the name itself. */
export function HandleName({ text }: { text: string }) {
  const match = /^(.*?)(#\d{4})$/.exec(text);
  if (!match) return <>{text}</>;
  return (
    <>
      {match[1]}
      <span className="handle-tag">{match[2]}</span>
    </>
  );
}
