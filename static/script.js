document.addEventListener('DOMContentLoaded', () => {
    const authSection = document.getElementById('auth-section');
    const mainSection = document.getElementById('main-section');
    const searchInput = document.getElementById('search');
    const objectType = document.getElementById('object-type');
    const objectsHeader = document.getElementById('objects-header');
    const objectsTable = document.getElementById('objects-table');
    const categoryTitle = document.getElementById('category-title');
    const deleteBtn = document.getElementById('delete-btn');
    const status = document.getElementById('status');

    let objects = [];
    let sortDirection = { Number: 1, Name: 1, Total: 1, Date: 1 }; // 1 = asc, -1 = desc
    let lastSortedColumn = 'Date'; // Default sort by Date ascending

    const categories = [
        { display: 'Bills', value: 'Bill', endpoint: 'bill?operation=delete&minorversion=75', condition: 'Unlink any linked transactions before deleting.' },
        { display: 'Bill Payments', value: 'BillPayment', endpoint: 'billpayment?operation=delete&minorversion=75', condition: null },
        { display: 'Budgets', value: 'Budget', endpoint: 'budget?operation=delete&minorversion=75', condition: null },
        { display: 'Credit Memos', value: 'CreditMemo', endpoint: 'creditmemo?operation=delete&minorversion=75', condition: null },
        { display: 'Credit Card Payments', value: 'CreditCardPayment', endpoint: 'creditcardpayment?operation=delete&minorversion=75', condition: null },
        { display: 'Customers', value: 'Customer', endpoint: 'customer?operation=delete&minorversion=75', condition: null },
        { display: 'Deposits', value: 'Deposit', endpoint: 'deposit?operation=delete&minorversion=75', condition: null },
        { display: 'Employees', value: 'Employee', endpoint: 'employee?operation=delete&minorversion=75', condition: null },
        { display: 'Estimates', value: 'Estimate', endpoint: 'estimate?operation=delete&minorversion=75', condition: null },
        { display: 'Inventory Adjustments', value: 'InventoryAdjustment', endpoint: 'inventoryadjustment?operation=delete&minorversion=75', condition: null },
        { display: 'Invoices', value: 'Invoice', endpoint: 'invoice?operation=delete&minorversion=75', condition: 'Unlink any linked transactions before deleting.' },
        { display: 'Journal Entries', value: 'JournalEntry', endpoint: 'journalentry?operation=delete&minorversion=75', condition: null },
        { display: 'Payments', value: 'Payment', endpoint: 'payment?operation=delete&minorversion=75', condition: null },
        { display: 'Purchases', value: 'Purchase', endpoint: 'purchase?operation=delete&minorversion=75', condition: null },
        { display: 'Purchase Orders', value: 'PurchaseOrder', endpoint: 'purchaseorder?operation=delete&minorversion=75', condition: 'Unlink any linked transactions before deleting.' },
        { display: 'Recurring Transactions', value: 'RecurringTransaction', endpoint: 'recurringtransaction?operation=delete&minorversion=75', condition: 'Unlink any linked transactions before deleting.' },
        { display: 'Refund Receipts', value: 'RefundReceipt', endpoint: 'refundreceipt?operation=delete&minorversion=75', condition: 'Unlink any linked transactions before deleting.' },
        { display: 'Sales Receipts', value: 'SalesReceipt', endpoint: 'salesreceipt?operation=delete&minorversion=75', condition: null },
        { display: 'Time Activities', value: 'TimeActivity', endpoint: 'timeactivity?operation=delete&minorversion=75', condition: null },
        { display: 'Transfers', value: 'Transfer', endpoint: 'transfer?operation=delete&minorversion=75', condition: null },
        { display: 'Vendor Credits', value: 'VendorCredit', endpoint: 'vendorcredit?operation=delete&minorversion=75', condition: null },
        { display: 'Vendors', value: 'Vendor', endpoint: 'vendor?operation=delete&minorversion=75', condition: null }
    ];
    objectType.innerHTML = categories.map(cat => `<option value="${cat.value}" data-endpoint="${cat.endpoint}" data-condition="${cat.condition || ''}">${cat.display}</option>`).join('');

    if (window.location.pathname === '/') {
        fetch('/check-auth', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        }).then(response => {
            if (response.ok) {
                return response.json().then(data => {
                    if (data.authenticated) {
                        authSection.style.display = 'none';
                        mainSection.style.display = 'block';
                        loadObjects();
                    } else {
                        status.textContent = 'Please connect to QuickBooks to proceed.';
                    }
                });
            } else {
                throw new Error(`Auth check failed with status: ${response.status}`);
            }
        }).catch(error => {
            status.textContent = 'Connection error during authentication check. Please try again.';
            console.error('Authentication check failed:', error);
        });
    }

    async function loadObjects() {
        try {
            status.textContent = 'Loading...';
            let endpoint;
            if (objectType.value === 'Expense') {
                endpoint = `query?query=SELECT * FROM Expense&minorversion=75`;
            } else if (objectType.value === 'Transaction') {
                endpoint = `transactionlist?minorversion=75`;
            } else {
                endpoint = `query?query=select * from ${objectType.value}`;
            }
            const response = await fetch('/api/qb', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ endpoint: endpoint })
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(`Load failed: ${response.status} - ${data.error}`);
            }
            const data = await response.json();
            console.log('Raw API response:', data);
            objects = (data.data?.QueryResponse?.[objectType.value] || []).sort((a, b) => {
                const dateA = a.TxnDate || a.MetaData?.CreateTime || '9999-12-31';
                const dateB = b.TxnDate || b.MetaData?.CreateTime || '9999-12-31';
                return new Date(dateA) - new Date(dateB); // Default: earliest to oldest
            });
            console.log('Loaded objects:', objects);
            renderHeaders();
            renderObjects(objects);
            status.textContent = '';
        } catch (error) {
            status.textContent = `Error loading objects: ${error.message}`;
            console.error('Load objects error:', error);
        }
    }

    function formatDate(dateStr) {
        if (!dateStr || dateStr === 'N/A') return 'N/A';
        const date = new Date(dateStr);
        const month = date.getMonth() + 1; // 0-based
        const day = date.getDate();
        const year = date.getFullYear().toString().slice(-2);
        return `${month}/${day < 10 ? '0' + day : day}/${year}`;
    }

    function sortObjects(column) {
        sortDirection[column] = lastSortedColumn === column ? -sortDirection[column] : 1;
        lastSortedColumn = column;

        objects.sort((a, b) => {
            let valA, valB;
            switch (column) {
                case 'Number':
                    valA = a.DocNumber || a.CheckNum || a.PaymentRefNum || a.Id || 'N/A';
                    valB = b.DocNumber || b.CheckNum || b.PaymentRefNum || b.Id || 'N/A';
                    return sortDirection[column] * valA.localeCompare(valB, undefined, { numeric: true, sensitivity: 'base' });
                case 'Name':
                    valA = a.Name || a.VendorRef?.name || a.CustomerRef?.name || 'N/A';
                    valB = b.Name || b.VendorRef?.name || b.CustomerRef?.name || 'N/A';
                    return sortDirection[column] * valA.localeCompare(valB);
                case 'Total':
                    valA = parseFloat(a.TotalAmt || 0);
                    valB = parseFloat(b.TotalAmt || 0);
                    return sortDirection[column] * (valA - valB);
                case 'Date':
                    valA = a.TxnDate || a.MetaData?.CreateTime || '9999-12-31';
                    valB = b.TxnDate || b.MetaData?.CreateTime || '9999-12-31';
                    return sortDirection[column] * (new Date(valA) - new Date(valB));
            }
        });
        renderHeaders(); // Update arrows
        renderObjects(objects); // Update sorted data
    }

    function renderHeaders() {
        objectsHeader.innerHTML = `
            <tr>
                <th><input type="checkbox" id="select-all" class="larger-checkbox"></th>
                <th data-column="Number">Number<span class="sort-arrow ${lastSortedColumn === 'Number' ? 'active' : ''}">${sortDirection['Number'] === 1 ? '↑' : '↓'}</span></th>
                <th data-column="Name">Name<span class="sort-arrow ${lastSortedColumn === 'Name' ? 'active' : ''}">${sortDirection['Name'] === 1 ? '↑' : '↓'}</span></th>
                <th data-column="Total">Total<span class="sort-arrow ${lastSortedColumn === 'Total' ? 'active' : ''}">${sortDirection['Total'] === 1 ? '↑' : '↓'}</span></th>
                <th data-column="Date">Date<span class="sort-arrow ${lastSortedColumn === 'Date' ? 'active' : ''}">${sortDirection['Date'] === 1 ? '↑' : '↓'}</span></th>
            </tr>
        `;

        const selectAllCheckbox = document.getElementById('select-all');
        selectAllCheckbox.addEventListener('change', () => {
            document.querySelectorAll('.object-select').forEach(cb => cb.checked = selectAllCheckbox.checked);
            updateDeleteButton();
        });

        const headers = objectsHeader.querySelectorAll('th');
        headers.forEach((th, index) => {
            if (index !== 0) { // Skip "Select" column
                th.addEventListener('click', () => {
                    const column = th.dataset.column;
                    sortObjects(column);
                });
            }
        });
    }

    function renderObjects(items) {
        categoryTitle.textContent = objectType.options[objectType.selectedIndex].text;

        if (items.length === 0) {
            objectsTable.innerHTML = `<tr><td colspan="5">No records here. Change the category on the dropdown to see more data.</td></tr>`;
            updateDeleteButton();
            return;
        }

        objectsTable.innerHTML = '';
        items.forEach(item => {
            const tr = document.createElement('tr');
            let number = '', name = '', total = '', date = '';
            switch (objectType.value) {
                case 'Bill':
                    number = item.DocNumber || 'N/A';
                    name = item.VendorRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'BillPayment':
                    number = item.CheckNum || item.Id || 'N/A';
                    name = item.VendorRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Budget':
                    number = item.Id || 'N/A';
                    name = item.Name || 'N/A';
                    total = 'N/A';
                    date = formatDate(item.MetaData?.CreateTime);
                    break;
                case 'CreditMemo':
                    number = item.DocNumber || 'N/A';
                    name = item.CustomerRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'CreditCardPayment':
                    number = item.Id || 'N/A';
                    name = item.AccountRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Customer':
                    number = item.Id || 'N/A';
                    name = item.DisplayName || 'N/A';
                    total = `$${item.Balance || 0}`;
                    date = formatDate(item.MetaData?.CreateTime);
                    break;
                case 'Deposit':
                    number = item.Id || 'N/A';
                    name = item.DepositToAccountRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Employee':
                    number = item.Id || 'N/A';
                    name = item.DisplayName || 'N/A';
                    total = 'N/A';
                    date = formatDate(item.MetaData?.CreateTime);
                    break;
                case 'Estimate':
                    number = item.DocNumber || 'N/A';
                    name = item.CustomerRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Expense':
                    number = item.DocNumber || item.Id || 'N/A';
                    name = item.Description || item.AccountRef?.name || 'N/A';
                    total = `$${item.TotalAmt || item.Amount || 0}`;
                    date = formatDate(item.TxnDate);
                    if (item.VendorRef?.name) {
                        name = `${name} (${item.VendorRef.name})`;
                    }
                    if (item.PaymentMethodRef?.name) {
                        name = `${name} - ${item.PaymentMethodRef.name}`;
                    }
                    break;
                case 'InventoryAdjustment':
                    number = item.Id || 'N/A';
                    name = item.AccountRef?.name || 'N/A';
                    total = 'N/A';
                    date = formatDate(item.TxnDate);
                    break;
                case 'Invoice':
                    number = item.DocNumber || 'N/A';
                    name = item.CustomerRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'JournalEntry':
                    number = item.DocNumber || 'N/A';
                    name = item.Description || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Payment':
                    number = item.PaymentRefNum || item.Id || 'N/A';
                    name = item.CustomerRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Purchase':
                    number = item.PaymentRefNum || item.Id || 'N/A';
                    name = item.AccountRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'PurchaseOrder':
                    number = item.DocNumber || 'N/A';
                    name = item.VendorRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'RecurringTransaction':
                    number = item.Id || 'N/A';
                    name = item.Description || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'RefundReceipt':
                    number = item.DocNumber || 'N/A';
                    name = item.CustomerRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'SalesReceipt':
                    number = item.DocNumber || 'N/A';
                    name = item.CustomerRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'TimeActivity':
                    number = item.Id || 'N/A';
                    name = item.EmployeeRef?.name || 'N/A';
                    total = 'N/A';
                    date = formatDate(item.TxnDate);
                    break;
                case 'Transaction':
                    number = item.Id || 'N/A';
                    name = item.Description || item.AccountRef?.name || 'N/A';
                    total = `$${item.Amount || 0}`;
                    date = formatDate(item.TxnDate);
                    if (item.AccountRef?.name) {
                        name = `${name} (${item.AccountRef.name})`;
                    }
                    if (item.EntityRef?.name) {
                        name = `${name} - ${item.EntityRef.name}`;
                    }
                    break;
                case 'Transfer':
                    number = item.Id || 'N/A';
                    name = item.FromAccountRef?.name + ' → ' + item.ToAccountRef?.name || 'N/A';
                    total = `$${item.Amount || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                case 'Vendor':
                    number = item.Id || 'N/A';
                    name = item.DisplayName || 'N/A';
                    total = `$${item.Balance || 0}`;
                    date = formatDate(item.MetaData?.CreateTime);
                    break;
                case 'VendorCredit':
                    number = item.DocNumber || 'N/A';
                    name = item.VendorRef?.name || 'N/A';
                    total = `$${item.TotalAmt || 0}`;
                    date = formatDate(item.TxnDate);
                    break;
                default:
                    number = item.DocNumber || item.Id || 'N/A';
                    name = item.Name || item.DisplayName || item.Description || 'N/A';
                    total = `$${item.TotalAmt || item.Balance || item.Amount || 0}`;
                    date = formatDate(item.TxnDate || item.MetaData?.CreateTime);
            }
            tr.innerHTML = `
                <td><input type="checkbox" class="object-select larger-checkbox" data-id="${item.Id}"></td>
                <td>${number}</td>
                <td>${name}</td>
                <td>${total}</td>
                <td>${date}</td>
            `;
            objectsTable.appendChild(tr);
        });
        updateDeleteButton();
    }

    searchInput.addEventListener('input', () => {
        const term = searchInput.value.toLowerCase();
        const filtered = objects.filter(obj => {
            const details = `${obj.DocNumber || obj.Id || ''} ${obj.Name || obj.VendorRef?.name || obj.CustomerRef?.name || ''} ${obj.TotalAmt || ''} ${obj.TxnDate || ''}`.toLowerCase();
            return details.includes(term);
        });
        renderObjects(filtered);
    });

    objectType.addEventListener('change', loadObjects);

    objectsTable.addEventListener('change', (e) => {
        if (e.target.classList.contains('object-select')) {
            updateDeleteButton();
            const allChecked = [...document.querySelectorAll('.object-select')].every(cb => cb.checked);
            document.getElementById('select-all').checked = allChecked;
        }
    });

    function updateDeleteButton() {
        const selected = document.querySelectorAll('.object-select:checked').length;
        deleteBtn.disabled = selected === 0;
        deleteBtn.textContent = `Delete Selected (${selected})`;
    }

    deleteBtn.addEventListener('click', async () => {
        const selectedIds = [...document.querySelectorAll('.object-select:checked')].map(cb => cb.dataset.id);
        const selectedOption = objectType.options[objectType.selectedIndex];
        const endpoint = selectedOption.dataset.endpoint;
        const condition = selectedOption.dataset.condition;

        if (!confirm(`Are you sure you want to permanently delete ${selectedIds.length} ${selectedOption.text}? This action is permanent and cannot be recovered.`)) return;

        // Show loading overlay
        const overlay = document.querySelector('.loading-overlay');
        overlay.classList.add('active');
        status.textContent = 'Deleting...';
        const results = { success: [], failed: [] };

        for (const id of selectedIds) {
            const item = objects.find(o => o.Id === id);
            try {
                const response = await fetch('/api/qb', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        endpoint: endpoint,
                        method: 'POST',
                        body: { Id: id, SyncToken: item.SyncToken },
                        entity_type: objectType.value
                    })
                });

                if (!response.ok) {
                    const data = await response.json();
                    let errorMsg = `${objectType.value} ${item.DocNumber || 'ID ' + id} - ${data.error?.Fault?.Error[0]?.Detail || data.error || 'The current row could not be deleted. This means Quickbooks is not allowing us to delete this row because certain conditions have not been met.'}`;
                    
                    // Check if this is a credit limit error
                    if (response.status === 403 && data.error.includes('monthly delete limit')) {
                        // Hide overlay before redirecting
                        overlay.classList.remove('active');
                        if (confirm('You have reached your monthly delete limit. Would you like to upgrade to unlimited deletes?')) {
                            window.location.href = '/pricing';
                            return;
                        }
                        // Show overlay again if user doesn't want to upgrade
                        overlay.classList.add('active');
                    }
                    
                    if (condition && data.error?.Fault?.Error[0]?.Detail?.includes('linked transactions')) {
                        errorMsg += `\nCondition not met: ${condition}`;
                    }
                    results.failed.push(errorMsg);
                } else {
                    results.success.push(`${objectType.value} ${item.DocNumber || 'ID ' + id}`);
                }
            } catch (error) {
                results.failed.push(`${objectType.value} ${item.DocNumber || 'ID ' + id} - The current row could not be deleted. This means Quickbooks is not allowing us to delete this row because certain conditions have not been met.`);
            }
        }

        // Hide loading overlay
        overlay.classList.remove('active');

        let message = '';
        if (results.success.length > 0) {
            message += `Successfully Deleted:\n${results.success.join('\n')}\n\n`;
        }
        if (results.failed.length > 0) {
            message += `Failed to Delete:\n${results.failed.join('\n')}`;
        }
        alert(message || 'No items processed.');
        status.textContent = '';
        setTimeout(loadObjects, 1000);
    });
});