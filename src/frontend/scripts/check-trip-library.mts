import assert from "node:assert/strict";
import {
  calendarDayForTrip,
  cardMeta,
  cardTitle,
  generationBadge,
  inDepartureYear,
  resolvedTimezone,
  secondaryMeta,
  timePartition,
  tripVisible,
} from "../src/lib/tripLibrary.ts";

const TODAY = "2026-09-24";
const YEAR = 2026;

const A = { id: "a", destination: "京都", start_date: null, end_date: null, status: "draft", people_count: 1, place_count: 0 };
const B = { id: "b", destination: "美食", city: "大阪", start_date: "2026-09-25", end_date: "2026-09-28", status: "generating", people_count: 2, place_count: 4 };
const C = { id: "c", destination: "火锅", city: "成都", start_date: "2026-10-01", end_date: "2026-10-05", status: "generation_failed", people_count: 2, place_count: 3 };
const D = { id: "d", destination: "周末", city: "杭州", start_date: "2026-05-01", end_date: "2026-05-05", status: "generated", people_count: 2, place_count: 8 };
const E = { id: "e", destination: "跨年", city: "北海道", start_date: "2026-12-28", end_date: "2027-01-05", status: "generated", people_count: 2, place_count: 6 };
const F = { id: "f", destination: "海岛", city: "厦门", start_date: "2026-11-10", end_date: "2026-11-14", status: "generated", people_count: 1, place_count: 5 };
const G = { id: "g", destination: "秋日", city: "东京", start_date: "2026-09-20", end_date: "2026-09-28", status: "generated", people_count: 2, place_count: 7 };
const Gp = { ...G, id: "gp", status: "generation_failed" };

const fixtures = [
  ["A", A, { all: true, upcoming: false, ongoing: false, past: false, undated: true, y2025: false, y2026: false, y2027: false }],
  ["B", B, { all: true, upcoming: true, ongoing: false, past: false, undated: false, y2025: false, y2026: true, y2027: false }],
  ["C", C, { all: true, upcoming: true, ongoing: false, past: false, undated: false, y2025: false, y2026: true, y2027: false }],
  ["D", D, { all: true, upcoming: false, ongoing: false, past: true, undated: false, y2025: false, y2026: true, y2027: false }],
  ["E", E, { all: true, upcoming: true, ongoing: false, past: false, undated: false, y2025: false, y2026: true, y2027: false }],
  ["F", F, { all: true, upcoming: true, ongoing: false, past: false, undated: false, y2025: false, y2026: true, y2027: false }],
  ["G", G, { all: true, upcoming: false, ongoing: true, past: false, undated: false, y2025: false, y2026: true, y2027: false }],
  ["Gp", Gp, { all: true, upcoming: false, ongoing: true, past: false, undated: false, y2025: false, y2026: true, y2027: false }],
] as const;

for (const [name, trip, expectRow] of fixtures) {
  assert.equal(tripVisible(trip, "all", YEAR, TODAY), expectRow.all, `${name} all`);
  assert.equal(tripVisible(trip, "upcoming", YEAR, TODAY), expectRow.upcoming, `${name} upcoming`);
  assert.equal(tripVisible(trip, "ongoing", YEAR, TODAY), expectRow.ongoing, `${name} ongoing`);
  assert.equal(tripVisible(trip, "past", YEAR, TODAY), expectRow.past, `${name} past`);
  assert.equal(tripVisible(trip, "undated", YEAR, TODAY), expectRow.undated, `${name} undated`);
  assert.equal(inDepartureYear(trip, 2025), expectRow.y2025, `${name} 2025`);
  assert.equal(inDepartureYear(trip, 2026), expectRow.y2026, `${name} 2026`);
  assert.equal(inDepartureYear(trip, 2027), expectRow.y2027, `${name} 2027`);
}

assert.equal(timePartition(null, null, TODAY), "undated");
assert.equal(timePartition("2026-09-25", "2026-09-28", TODAY), "upcoming");
assert.equal(timePartition("2026-09-20", "2026-09-28", TODAY), "ongoing");
assert.equal(timePartition("2026-05-01", "2026-05-05", TODAY), "past");
assert.equal(timePartition("2026-09-24", "2026-09-24", TODAY), "ongoing");

assert.equal(cardTitle(A), "京都");
assert.equal(cardTitle(B), "大阪 · 美食");
assert.equal(cardMeta(A), "日期待定 · 人数未定");
assert.equal(cardMeta(E), "2026/12/28 – 2027/01/05 · 9 天 · 2 人");
assert.equal(cardMeta(D), "05/01 – 05/05 · 5 天 · 2 人");
assert.equal(generationBadge(B.status), "planning");
assert.equal(generationBadge(C.status), "retry");
assert.equal(generationBadge(D.status), null);
assert.equal(generationBadge(A.status), "draft");
assert.equal(secondaryMeta(B), "规划中…");
assert.equal(secondaryMeta(C), "可重试");
assert.equal(secondaryMeta(A), "尚未生成");
assert.equal(secondaryMeta(D), "8 个地点");

const BOUNDARY = "2026-09-24T15:30:00Z";
const osaka = { city: "大阪", destination: "美食", timezone: null };
const chengdu = { city: "成都", destination: "火锅", timezone: null };
const honolulu = { city: "檀香山", destination: "海岛", timezone: null };
const unknown = { city: "无名镇", destination: "草稿", timezone: null };
assert.equal(resolvedTimezone(osaka), "Asia/Tokyo");
assert.equal(resolvedTimezone(chengdu), "Asia/Shanghai");
assert.equal(resolvedTimezone(honolulu), "Pacific/Honolulu");
assert.equal(resolvedTimezone(unknown), null);
assert.equal(calendarDayForTrip(osaka, new Date(BOUNDARY), null), "2026-09-25");
assert.equal(calendarDayForTrip(chengdu, new Date(BOUNDARY), null), "2026-09-24");
assert.equal(calendarDayForTrip(honolulu, new Date(BOUNDARY), null), "2026-09-24");
assert.equal(calendarDayForTrip(osaka, new Date(BOUNDARY), BOUNDARY), "2026-09-25");
assert.equal(calendarDayForTrip(chengdu, new Date("2026-09-25T00:00:00Z"), "2026-09-24"), "2026-09-24");
assert.equal(
  timePartition(B.start_date, B.end_date, calendarDayForTrip(osaka, new Date(BOUNDARY), null)),
  "ongoing",
);
assert.equal(
  timePartition(B.start_date, B.end_date, calendarDayForTrip(chengdu, new Date(BOUNDARY), null)),
  "upcoming",
);
assert.equal(calendarDayForTrip(unknown, new Date("2026-09-24T16:00:00Z"), null).length, 10);

console.log("trip library A–G checks passed");
