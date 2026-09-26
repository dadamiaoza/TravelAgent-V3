import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  libraryDegradationSignal,
  shortWarningCopy,
  warningMessages,
} from "./degradationCopy.ts";

describe("shortWarningCopy", () => {
  it("keeps a short clause and truncates the rest", () => {
    assert.equal(shortWarningCopy("时效核对未完成，行程已按路线生成"), "时效核对未完成，行程已按路线生成");
    assert.equal(shortWarningCopy("甲；乙"), "甲");
    const long = "一二三四五六七八九十一二三四五六七八九十一二三四五";
    assert.equal(long.length, 25);
    assert.equal(shortWarningCopy(long), `${long.slice(0, 24)}…`);
    assert.equal(shortWarningCopy("   "), "生成有降级");
  });
});

describe("warningMessages", () => {
  it("returns every warning stage in order and ignores other keys", () => {
    const messages = warningMessages({
      stages: [
        { key: "route", progress: 70, message: "正在补路线...", at: "1" },
        { key: "warning", progress: 75, message: "第1天已按最近邻重排（路时明显绕路）", at: "2" },
        { key: "warning", progress: 75, message: " 第1天已按最近邻重排（路时明显绕路） ", at: "3" },
        { key: "warning", progress: 75, message: "跨天衔接偏远", at: "4" },
        { key: "warning", progress: 95, message: "时效核对未完成，行程已按路线生成", at: "5" },
      ],
    });
    assert.deepEqual(messages, [
      "第1天已按最近邻重排（路时明显绕路）",
      "跨天衔接偏远",
      "时效核对未完成，行程已按路线生成",
    ]);
  });

  it("returns nothing when the job has no warning stages", () => {
    assert.deepEqual(warningMessages({ stages: [{ key: "done", progress: 100, message: "行程生成完成", at: "1" }] }), []);
    assert.equal(libraryDegradationSignal([]), null);
    assert.equal(libraryDegradationSignal(undefined), null);
  });
});

describe("libraryDegradationSignal", () => {
  it("uses one short chip, and names the count when several apply", () => {
    assert.deepEqual(libraryDegradationSignal(["第2天已按最近邻重排（顺序无效）"]), {
      label: "第2天已按最近邻重排（顺序无效）",
      title: "第2天已按最近邻重排（顺序无效）",
    });
    const signal = libraryDegradationSignal([
      "第1天已按最近邻重排（路时明显绕路）",
      "第1天终点与第2天起点相距约 300 公里，跨天衔接偏远。本次不会自动把景点改到另一天。",
    ]);
    assert.equal(signal?.label, "第1天已按最近邻重排（路时明显绕路） 等2项");
    assert.match(signal?.title ?? "", /300 公里/);
    assert.match(signal?.title ?? "", /最近邻/);
  });
});
