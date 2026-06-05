#!/usr/bin/env node
import { Innertube, YTNodes } from "youtubei.js";

function argValue(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) return "";
  return process.argv[index + 1] || "";
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function emitError(error, fatal = false) {
  emit({
    type: fatal ? "fatal" : "error",
    message: error instanceof Error ? error.message : String(error),
  });
}

function isMember(author) {
  const badges = author?.badges;
  if (!badges || typeof badges.some !== "function") return false;
  return badges.some((badge) => {
    try {
      return badge.is(YTNodes.LiveChatAuthorBadge)
        && badge.as(YTNodes.LiveChatAuthorBadge).custom_thumbnail.length > 0;
    } catch {
      return false;
    }
  });
}

function toMessage(item) {
  let msg = null;
  try {
    if (item.is(YTNodes.LiveChatTextMessage)) {
      msg = item.as(YTNodes.LiveChatTextMessage);
    } else if (item.is(YTNodes.LiveChatPaidMessage)) {
      msg = item.as(YTNodes.LiveChatPaidMessage);
    }
  } catch {
    return null;
  }
  if (!msg) return null;
  return {
    type: "message",
    id: String(msg.id || ""),
    author: String(msg.author?.name || ""),
    text: String(msg.message?.toString() || "").trim(),
    timestamp: Number.isFinite(msg.timestamp)
      ? new Date(msg.timestamp).toISOString()
      : new Date().toISOString(),
    isModerator: Boolean(msg.author?.is_moderator),
    isMember: isMember(msg.author),
    authorChannelId: msg.author?.id && msg.author.id !== "N/A" ? String(msg.author.id) : "",
  };
}

async function main() {
  const videoId = argValue("--video-id");
  if (!/^[\w-]{11}$/.test(videoId)) {
    throw new Error("--video-id must be an 11-character YouTube video id");
  }

  const yt = await Innertube.create();
  const info = await yt.getInfo(videoId);
  const livechat = info.getLiveChat();

  livechat.on("chat-update", (action) => {
    try {
      if (!action.is(YTNodes.AddChatItemAction)) return;
      const item = action.as(YTNodes.AddChatItemAction).item;
      if (!item) return;
      const message = toMessage(item);
      if (message) emit(message);
    } catch (error) {
      emitError(error);
    }
  });

  livechat.on("error", (error) => {
    emitError(error);
  });

  livechat.on("end", () => {
    emit({ type: "end" });
  });

  const stop = () => {
    try {
      livechat.stop();
    } catch {
      // ignore shutdown errors
    }
    emit({ type: "stopped" });
    process.exit(0);
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);

  livechat.start();
  emit({ type: "ready", videoId });
}

main().catch((error) => {
  emitError(error, true);
  process.exit(1);
});
