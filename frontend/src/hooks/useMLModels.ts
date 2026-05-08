import { useQuery } from "@tanstack/react-query";
import { listModels } from "@/api/ml";

export function useMLModels() {
  return useQuery({
    queryKey: ["ml-models"],
    queryFn: listModels,
    staleTime: 120_000,
  });
}
