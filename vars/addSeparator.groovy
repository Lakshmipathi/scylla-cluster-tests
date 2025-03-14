// vars/addSeparator.groovy
def call(Map params) {
    separator(
        name: params.name,
        sectionHeader: params.sectionHeader,
        separatorStyle: "border-width: 0",
        sectionHeaderStyle: """
            background-color: #7ea6d3;
            text-align: center;
            padding: 4px;
            color: #343434;
            font-size: 22px;
            font-weight: normal;
            text-transform: uppercase;
            font-family: 'Orienta', sans-serif;
            letter-spacing: 1px;
            font-style: italic;
        """
    )
}

