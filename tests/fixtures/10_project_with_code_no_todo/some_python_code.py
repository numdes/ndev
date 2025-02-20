def sort(arr):
    # TODO: optimize this code
    n = len(arr)
    # Traverse through all elements in the list
    for i in range(n):
        # Last i elements are already sorted
        for j in range(n - i - 1):
            # Swap if the element found is greater than the next element
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr


# Example usage
arr = [64, 34, 25, 12, 22, 11, 90]
sorted_arr = sort(arr)
print("Sorted array:", sorted_arr)
