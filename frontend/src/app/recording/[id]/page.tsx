import RecordingDetail from './RecordingDetail';

/**
 * Recording Detail Page (Server Component)
 * ---------------------------------------
 * Handles static generation params for Next.js static export.
 * Delegates all interactive UI logic to the RecordingDetail Client Component.
 */

export async function generateStaticParams() {
  // For static export, we return an empty array to indicate that IDs 
  // will be handled dynamically on the client side at runtime.
  return [];
}

export default function RecordingPage({ params }: { params: { id: string } }) {
  return <RecordingDetail id={params.id} />;
}
