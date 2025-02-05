// app.js

// If using Node.js version earlier than 18, uncomment the next line and install node-fetch
// const fetch = require('node-fetch'); // Uncomment if using Node.js < 18

const readline = require('readline');

// Function to get input from the console
function promptUser(query) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve) => rl.question(query, (answer) => {
    rl.close();
    resolve(answer.trim());
  }));
}

// Function to get user approval for research queries
async function getResearchQueriesApproval(generatedQueries) {
  console.log("\n===== Generated Research Queries =====");
  generatedQueries.forEach((query, index) => {
    console.log(`${index + 1}. ${query}`);
  });
  console.log("======================================\n");

  const approveInput = await promptUser('Would you like to modify or add queries? (yes/no): ');
  const approve = approveInput.trim().toLowerCase() === 'yes';

  let approvedQueries = generatedQueries;

  if (approve) {
    approvedQueries = [];
    const queryCountInput = await promptUser('How many queries would you like to provide?: ');
    const queryCount = parseInt(queryCountInput, 10);

    for (let i = 0; i < queryCount; i++) {
      const newQuery = await promptUser(`Enter query ${i + 1}: `);
      approvedQueries.push(newQuery);
    }
  }

  return approvedQueries;
}

// Function to simulate getting user approval with actual console input
async function getUserApproval(current_text) {
  console.log("\n===== AI-Generated Modified Text =====");
  console.log(current_text);
  console.log("======================================\n");

  let approvedInput = await promptUser('Do you approve the changes? (yes/no): ');
  while (approvedInput.toLowerCase() !== 'yes' && approvedInput.toLowerCase() !== 'no') {
    console.log("Please enter 'yes' or 'no'.");
    approvedInput = await promptUser('Do you approve the changes? (yes/no): ');
  }
  const approved = approvedInput.toLowerCase() === 'yes';

  let modifications = '';
  if (!approved) {
    modifications = await promptUser('Please provide your modifications (leave blank if none): ');
  }

  return { approved, modifications };
}

// Main function to execute the API calls
(async () => {
  try {
    // Get initial input from the user
    const message = await promptUser('Enter your message: ');
    const sectionNumberInput = await promptUser('Enter the section number: ');
    const section_number = parseInt(sectionNumberInput, 10);

    // First API request
    let response = await fetch('http://127.0.0.1:8000/process-input', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message, section_number })
    });

    let result = await response.json();

    // Handle pending query modification
    while (result.status === 'pending_query_modification') {
      // Get user-approved research queries
      const approvedQueries = await getResearchQueriesApproval(result.generated_research_queries);

      // Make a new request including user-approved research queries
      response = await fetch('http://127.0.0.1:8000/process-input', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message,
          section_number,
          user_approved_research_queries: approvedQueries
        })
      });

      result = await response.json();
    }

    // Handle pending human input
    while (result.status === 'pending_human_input') {
      // Show current_text to user and get their approval
      const userApproval = await getUserApproval(result.current_text);

      // Make second request with approval
      response = await fetch('http://127.0.0.1:8000/process-input', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message,
          section_number,
          human_approval: userApproval.approved ? 'yes' : 'no',
          user_modifications: userApproval.modifications
        })
      });

      result = await response.json();
    }

    // Final Result
    console.log("\n===== Final Result from API =====");
    console.log(result);
    console.log("==================================\n");

  } catch (error) {
    console.error("Error during API calls:", error);
  }
})();
