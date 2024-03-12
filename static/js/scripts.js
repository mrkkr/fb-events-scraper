/** enable dark mode */
if (window.matchMedia &&
  window.matchMedia('(prefers-color-scheme: dark)').matches) {
document.body.classList.add('dark');
}

/**
* Datepicker
*/
// Get references to datepicker inputs
const startDatePicker = document.getElementById('startDatePicker');
const endDatePicker = document.getElementById('endDatePicker');

// Collect all elements with a `date-atr` attribute
const elements = document.querySelectorAll('[date-atr]');

// Event handler for date changes
function handleDateChange() {
// Parse the dates from the inputs; assume they're in ISO format (yyyy-mm-dd) from <input type="date">
const startDate = startDatePicker.value ? new Date(startDatePicker.value) : null;
const endDate = endDatePicker.value ? new Date(endDatePicker.value) : null;

// Ensure both dates are selected; otherwise, show all elements
if (startDate && endDate) {
  // Create new Date objects with time set to midnight (00:00:00)
  const startDateMidnight = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
  const endDateMidnight = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());

  elements.forEach(element => {
    const elementDateStr = element.getAttribute('date-atr');
    const elementDateParts = elementDateStr.split('/'); // Split the date string
    // Create a Date object from the parsed date parts (assuming day/month/year format)
    const elementDate = new Date(elementDateParts[2], elementDateParts[1] - 1, elementDateParts[0]);

    // Create new Date object for elementDate with time set to midnight and year set to the current year
    const elementDateMidnight = new Date(new Date().getFullYear(), elementDate.getMonth(), elementDate.getDate());

    if (elementDateMidnight >= startDateMidnight && elementDateMidnight <= endDateMidnight) {
      // Show elements within the date range
      element.classList.remove("inactive");
      element.classList.add("active");
    } else {
      // Hide elements outside the date range
      element.classList.add("inactive");
      element.classList.remove('active');
    }
  });
} else {
  // If not both dates are selected, reset the visibility
  elements.forEach(element => {
    element.classList.remove("inactive");
    element.classList.remove("active");
  });
}
}

// Bind the change event handler to both datepickers
startDatePicker.addEventListener('change', handleDateChange);
endDatePicker.addEventListener('change', handleDateChange);

// Optional: Implementation for clearing the date range and resetting element visibility
function clearDateRange() {
startDatePicker.value = '';
endDatePicker.value = '';
// Show all elements
elements.forEach(element => {
  element.classList.remove("inactive");
  element.classList.remove("active");
});
}

// Optional: Implement a clear button functionality
document.getElementById('clear-dates').addEventListener('click', clearDateRange);

// Ensure this function exists or add a button with id 'clearDates' if you'd like to use it


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
