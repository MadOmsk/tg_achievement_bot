import "./Skeleton.css";

export function PageSkel() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="skel hero" />
      <span className="skel line" />
      <span className="skel line" style={{ width: "68%" }} />
      <div className="skel-row">
        <span className="skel circle" style={{ width: 58, height: 58 }} />
        <span>
          <span className="skel line" />
          <span className="skel line" style={{ width: "55%" }} />
        </span>
      </div>
      <div className="skel-row">
        <span className="skel circle" style={{ width: 58, height: 58 }} />
        <span>
          <span className="skel line" />
          <span className="skel line" style={{ width: "48%" }} />
        </span>
      </div>
    </div>
  );
}

export function HomeSkel() {
  return (
    <div className="profile-hero home-skel" aria-busy="true">
      <span className="skel home-skel-fill" />
    </div>
  );
}
