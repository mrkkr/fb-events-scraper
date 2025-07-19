document.addEventListener('DOMContentLoaded', function () {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const eventContainers = document.querySelectorAll('.event-container');
    const dateSections = document.querySelectorAll('.date-section');
    
    const filterTrigger = document.getElementById('filter-trigger');
    const categoryList = document.getElementById('category-list');

    const updateDateVisibility = () => {
        dateSections.forEach(section => {
            const visibleEvents = section.querySelectorAll('.event-container:not(.hidden)');
            
            if (visibleEvents.length === 0) {
                section.classList.add('hidden');
            } else {
                section.classList.remove('hidden');
            }
        });
    };

    const applyFilter = (filterCategory) => {
        eventContainers.forEach(container => {
            const eventCategories = container.getAttribute('data-categories');
            const shouldBeVisible = (filterCategory === 'all' || eventCategories.includes(filterCategory));

            if (shouldBeVisible) {
                container.classList.remove('hidden');
            } else {
                container.classList.add('hidden');
            }
        });
        updateDateVisibility();
    };

    filterButtons.forEach(button => {
        button.addEventListener('click', () => {
            const filterCategory = button.getAttribute('data-category');
            const categoryName = button.textContent;

            filterButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            applyFilter(filterCategory);

            if (window.getComputedStyle(filterTrigger).display !== 'none') {
                filterTrigger.textContent = categoryName;
                categoryList.classList.remove('is-open');
            }
        });
    });

    if (filterTrigger) {
        filterTrigger.addEventListener('click', (event) => {
            event.stopPropagation();
            categoryList.classList.toggle('is-open');
        });
    }

    document.addEventListener('click', (event) => {
        if (categoryList && categoryList.classList.contains('is-open')) {
            if (!categoryList.contains(event.target) && event.target !== filterTrigger) {
                categoryList.classList.remove('is-open');
            }
        }
    });

    updateDateVisibility();
});
