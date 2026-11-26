import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { api, type ChunkSettings, errorText } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

const suggestName = (settings: ChunkSettings) => `${settings.chunker === "heading" ? "h" : "f"}${settings.size}-o${settings.overlap}`;

export function SaveDialog({ indexId, settings, chunks, disabled }: { indexId: number; settings: ChunkSettings; chunks: number; disabled: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  const save = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/chunk-lab/indexes", { body: { index_id: indexId, name, ...settings } });
      if (!data) throw new Error(errorText(error));
      return data;
    },
    onSuccess: async ({ id }) => {
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      navigate({ to: "/datasets", search: { index: id } });
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        save.reset();
        if (next) setName(suggestName(settings));
      }}
    >
      <DialogTrigger render={<Button className="bg-brand h-9 rounded-xl px-5 font-semibold shadow-blue" disabled={disabled} />}>存为索引版本</DialogTrigger>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>存为新的索引版本</DialogTitle>
          <DialogDescription>
            全库约切成 {chunks.toLocaleString()} 块，马上开始算向量。现有的索引版本不受影响，建好后可以拿去评测对比。
          </DialogDescription>
        </DialogHeader>
        <Input value={name} onChange={(event) => setName(event.target.value)} aria-label="版本名" maxLength={50} className="h-10 rounded-xl" />
        {save.error && <p className="text-[13px] text-down">{save.error.message}</p>}
        <DialogFooter>
          <Button className="bg-brand rounded-xl px-5" disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>
            {save.isPending ? "创建中" : "开始建索引"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
