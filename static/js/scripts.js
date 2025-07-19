/**
* Lazy loading
*/
// Function to count the total number of items with class "lazy"
function countItems() {
  return document.querySelectorAll('.lazy').length;
}

// Total number of items
const totalItems = countItems();
console.log(totalItems);

// Number of items to load per batch
const itemsPerBatch = 3;

// Index to keep track of the last loaded item
let lastIndex = 2;

// Function to load items
function loadItems() {
  // Load items in batches
  for (let i = lastIndex; i < Math.min(totalItems, lastIndex + itemsPerBatch); i++) {
      // Get the item by index and show it
      const item = document.querySelector('.lazy:nth-child(' + (i + 1) + ')');
      if (item) {
        item.style.opacity = 1;
        item.style.display = "block";
      }
  }
  // Update the last loaded index
  lastIndex += itemsPerBatch;
}

// Initial loading
loadItems();

// Event listener for scrolling
window.addEventListener('scroll', () => {
  // Check if user has scrolled to the bottom of the visible content
  if ((window.innerHeight + window.scrollY) >= document.body.scrollHeight) {
      // Load more items
      loadItems();
  }
});

/**
* Back to top
*/
// Get the button element
const backToTopBtn = document.getElementById('backToTopBtn');

// Function to scroll back to the top of the page
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth' // Smooth scroll behavior
    });
}

// Event listener for scrolling
window.addEventListener('scroll', () => {
    // If the user has scrolled down more than the height of the viewport, show the button, otherwise hide it
    if (window.scrollY > window.innerHeight) {
        backToTopBtn.style.display = 'block';
    } else {
        backToTopBtn.style.display = 'none';
    }
});

// Event listener for clicking the button
backToTopBtn.addEventListener('click', scrollToTop);
