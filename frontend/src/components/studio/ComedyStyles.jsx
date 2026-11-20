import "@/styles/comedy-styles.css";

const STYLES = [
  ["savage", "Savage"], ["dark", "Dark comedy"], ["street_battle", "Street battle"],
  ["sarcastic", "Sarcastic"], ["intellectual", "Intellectual"], ["absurdist", "Absurdist"],
  ["southern_country", "Southern / country"], ["old_school", "Old-school"],
  ["celebrity_roast", "Celebrity roast"], ["freestyle", "Freestyle"],
];

export function ComedyStyles({ value, onChange }) {
  const toggle = (style) => onChange((current) => current.includes(style)
    ? current.filter((item) => item !== style) : [...current, style]);
  return <fieldset className="comedy-styles" data-testid="comedy-styles">
    <legend>Comedy styles <span>· optional, mix and match</span></legend>
    <p>Give the selected roasters a creative direction. Heat, clean mode and your boundaries still apply.</p>
    <div className="comedy-styles-grid">{STYLES.map(([id, label]) => <label className={`comedy-style ${value.includes(id) ? "selected" : ""}`} key={id}>
      <input type="checkbox" checked={value.includes(id)} onChange={() => toggle(id)} data-testid={`comedy-style-${id}`} />
      <span>{label}</span>
    </label>)}</div>
  </fieldset>;
}
