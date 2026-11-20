import { PersonaBrowser } from "@/components/PersonaBrowser";

export const RosterPicker = ({ personas, selected, onToggle, onRandom, max }) => (
  <PersonaBrowser personas={personas} selected={selected} onSelect={onToggle} onRandom={onRandom} max={max} mode="studio" />
);
