async function loadUser(id) {
  try {
    const response = await fetch(`https://jsonplaceholder.typicode.com/users/${id}`);

    if (!response.ok) {                        // fetch does NOT throw on 404/500!
      throw new Error(`Request failed: ${response.status}`);
    }

    const user = await response.json();        // parsing the body is async too
    return user;
  } catch (error) {
    console.error("Could not load user:", error.message);
    return null;
  }
}

async function main() {
  const user = await loadUser(1);
  console.log(user?.name);
}

main();
