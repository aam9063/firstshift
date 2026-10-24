/* One date format for the whole console: dd/mm/yyyy HH:mm, local time.
   ISO timestamps arrive from the API; long ISO strings overflowed the journey
   timeline, so every timestamp renders through this helper. */

function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    // Never invent a date: show what the backend sent.
    return value;
  }
  return (
    `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
