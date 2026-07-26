const fs = require('fs');
const path = "C:/Users/KIIT/.claude/projects/E--claude-skills-job-hunt-agent/cf8cb027-06c3-4ff0-bb68-5d1c473cb45a/tool-results/toolu_01BnsidGiFwnptbtxrqPiyHu.json";
const raw = fs.readFileSync(path, 'utf8');
const data = JSON.parse(raw);
console.log("Number of entries:", data.length);
data.forEach((entry, i) => {
  console.log(`--- Entry ${i} ---`);
  console.log("url:", entry.url);
  console.log("title:", entry.title);
  const textLen = entry.text ? entry.text.length : 0;
  const linksLen = entry.links ? entry.links.length : 0;
  console.log("text length (chars):", textLen);
  console.log("links count:", linksLen);
  console.log("keys:", Object.keys(entry));
});
