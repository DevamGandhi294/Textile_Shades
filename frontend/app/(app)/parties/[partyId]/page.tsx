import { PartiesView } from "@/components/parties-view";

export default async function PartyPage({ params }: { params: Promise<{ partyId: string }> }) {
  const { partyId } = await params;
  return <PartiesView partyId={partyId} />;
}
