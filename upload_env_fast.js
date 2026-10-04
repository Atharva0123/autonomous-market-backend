const fs = require('fs');
const { exec } = require('child_process');

const envContent = fs.readFileSync('.env', 'utf8');
const lines = envContent.split('\n');

const tasks = [];

for (const line of lines) {
  const match = line.match(/^\s*([^#\s=]+)\s*=\s*(.*)$/);
  if (match) {
    const key = match[1];
    let val = match[2].trim();
    if (val.startsWith('"') && val.endsWith('"')) {
      val = val.slice(1, -1);
    } else if (val.startsWith("'") && val.endsWith("'")) {
      val = val.slice(1, -1);
    }
    if (val) {
      tasks.push({ key, val });
    }
  }
}

async function uploadAll() {
  console.log(`Found ${tasks.length} variables to upload.`);
  const promises = tasks.map((task) => {
    return new Promise((resolve) => {
      const child = exec(`npx vercel env add ${task.key} production`, (error, stdout, stderr) => {
        if (error) {
          console.error(`Failed to add ${task.key}:`, stderr);
        } else {
          console.log(`Added ${task.key}`);
        }
        resolve();
      });
      child.stdin.write(task.val + '\n');
      child.stdin.end();
    });
  });
  
  await Promise.all(promises);
  console.log("All variables uploaded successfully.");
}

uploadAll();
